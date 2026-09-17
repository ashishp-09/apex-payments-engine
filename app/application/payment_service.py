import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.application.idempotency_service import IdempotencyService
from app.application.payment_saga import PaymentSaga
from app.application.schemas import CreatePaymentRequest, PaymentResponse
from app.domain.enums import AuthorizationOutcome, PaymentStatus
from app.domain.exceptions import PaymentNotFoundException
from app.domain.models import Payment
from app.infrastructure.psp.provider import PaymentProvider


class PaymentService:
    def __init__(
        self,
        saga: PaymentSaga,
        idempotency: IdempotencyService,
        psp: PaymentProvider,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.saga = saga
        self.idempotency = idempotency
        self.psp = psp
        self.session_factory = session_factory

    async def get_payment(self, payment_id: uuid.UUID) -> PaymentResponse:
        async with self.session_factory() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            res = await session.execute(stmt)
            payment = res.scalar_one_or_none()
            if not payment:
                raise PaymentNotFoundException(payment_id)
            return self._to_response(payment)

    async def create(self, idempotency_key: str, request: CreatePaymentRequest) -> tuple[int, PaymentResponse]:
        req_dict = request.model_dump(mode="json")
        payment_id = uuid.uuid4()

        # -------------------------------------------------------------
        # 1. Transaction 1: Idempotency Claim & Hold Funds
        # -------------------------------------------------------------
        async with self.session_factory() as session:
            async with session.begin():
                replay = await self.idempotency.claim_or_replay(
                    session, request.merchantId, idempotency_key, req_dict
                )
                if replay is not None:
                    status_code, body = replay
                    return status_code, PaymentResponse(**body)

                # Initialize Payment Record
                payment = Payment(
                    id=payment_id,
                    merchant_id=request.merchantId,
                    payer_account=request.payerAccountId,
                    payee_account=request.payeeAccountId,
                    amount=request.amount,
                    currency=request.currency,
                    status=PaymentStatus.CREATED,
                    created_at=datetime.now(timezone.utc),
                )
                # Phase 1: Hold (Locks funds into SUSPENSE)
                await self.saga.hold(session, payment)

        # -------------------------------------------------------------
        # 2. Network I/O: External PSP Call (Strictly Outside DB Locks)
        # -------------------------------------------------------------
        auth_result = await self.psp.authorize(payment)

        # -------------------------------------------------------------
        # 3. Transaction 2: Settle / Compensate & Complete Idempotency
        # -------------------------------------------------------------
        async with self.session_factory() as session:
            async with session.begin():
                if auth_result.outcome == AuthorizationOutcome.CAPTURED:
                    payment = await self.saga.settle(session, payment_id, auth_result.psp_reference or "")
                elif auth_result.outcome == AuthorizationOutcome.DECLINED:
                    payment = await self.saga.reverse(session, payment_id)
                elif auth_result.outcome == AuthorizationOutcome.PENDING:
                    # Stored in AUTHORIZED state waiting for webhook
                    stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
                    res = await session.execute(stmt)
                    payment = res.scalar_one()
                    payment.status = PaymentStatus.AUTHORIZED
                    payment.psp_reference = auth_result.psp_reference

                response = self._to_response(payment)
                await self.idempotency.complete(
                    session,
                    merchant_id=request.merchantId,
                    idem_key=idempotency_key,
                    resource_id=payment.id,
                    response_code=201,
                    response_body=response.model_dump(mode="json"),
                )

        return 201, response

    @staticmethod
    def _to_response(payment: Payment) -> PaymentResponse:
        return PaymentResponse(
            id=payment.id,
            merchantId=payment.merchant_id,
            payerAccountId=payment.payer_account,
            payeeAccountId=payment.payee_account,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            pspReference=payment.psp_reference,
            refundedAmount=payment.refunded_amount,
            createdAt=payment.created_at,
        )
