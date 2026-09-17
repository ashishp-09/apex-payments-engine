import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.idempotency_service import IdempotencyService
from app.application.ledger_service import LedgerService, Posting
from app.application.schemas import RefundRequest, RefundResponse
from app.domain.enums import Direction, PaymentStatus, RefundStatus, TransactionType
from app.domain.exceptions import PaymentNotFoundException, RefundNotAllowedException
from app.domain.models import Outbox, Payment, Refund


class RefundService:
    def __init__(self, ledger_service: LedgerService, idempotency_service: IdempotencyService):
        self.ledger = ledger_service
        self.idempotency = idempotency_service

    async def refund(
        self,
        session: AsyncSession,
        idempotency_key: str,
        payment_id: uuid.UUID,
        amount: int,
    ) -> tuple[int, RefundResponse]:
        # 1. Idempotency Check
        payload = {"payment_id": str(payment_id), "amount": amount}
        replay = await self.idempotency.claim_or_replay(session, "merchant_refund", idempotency_key, payload)
        if replay is not None:
            code, body = replay
            return code, RefundResponse(**body)

        # 2. Lock Payment under SELECT ... FOR UPDATE
        stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
        res = await session.execute(stmt)
        payment = res.scalar_one_or_none()
        if not payment:
            raise PaymentNotFoundException(payment_id)

        if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUND_PENDING):
            raise RefundNotAllowedException(f"Cannot refund payment with status: {payment.status.value}")

        if payment.refunded_amount + amount > payment.amount:
            raise RefundNotAllowedException(
                f"Refund amount {amount} exceeds capturable balance ({payment.amount - payment.refunded_amount})"
            )

        # 3. Create Refund record
        refund_id = uuid.uuid4()
        refund_record = Refund(
            id=refund_id,
            payment_id=payment.id,
            amount=amount,
            status=RefundStatus.SUCCEEDED,
            created_at=datetime.now(timezone.utc),
        )
        session.add(refund_record)

        # Update Payment
        payment.refunded_amount += amount
        if payment.refunded_amount == payment.amount:
            payment.status = PaymentStatus.REFUNDED
        payment.version += 1
        payment.updated_at = datetime.now(timezone.utc)

        # 4. Post Ledger Reversal (Debit Payee, Credit Payer)
        postings = [
            Posting(account_id=payment.payee_account, direction=Direction.DEBIT, amount=amount),
            Posting(account_id=payment.payer_account, direction=Direction.CREDIT, amount=amount),
        ]
        await self.ledger.post(session, TransactionType.REFUND, refund_id, postings)

        # 5. Outbox Event
        outbox_event = Outbox(
            aggregate_type="refund",
            aggregate_id=refund_id,
            event_type="refund.completed",
            payload={
                "refundId": str(refund_id),
                "paymentId": str(payment.id),
                "amount": amount,
                "status": refund_record.status.value,
            },
        )
        session.add(outbox_event)

        response = RefundResponse(
            id=refund_id,
            paymentId=payment.id,
            amount=amount,
            status=refund_record.status,
            createdAt=refund_record.created_at,
        )

        # 6. Complete Idempotency
        await self.idempotency.complete(
            session,
            merchant_id="merchant_refund",
            idem_key=idempotency_key,
            resource_id=refund_id,
            response_code=201,
            response_body=response.model_dump(mode="json"),
        )

        return 201, response
