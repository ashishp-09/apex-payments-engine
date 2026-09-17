import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ledger_service import LedgerService, Posting
from app.domain.enums import Direction, PaymentStatus, TransactionType
from app.domain.exceptions import PaymentNotFoundException
from app.domain.models import Outbox, Payment

PSP_SUSPENSE_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
FEE_INCOME_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class PaymentSaga:
    """
    Orchestrates the Hold -> Authorize -> Settle/Reverse saga.
    DB Transactions are strictly isolated from external PSP network I/O.
    """

    def __init__(self, ledger_service: LedgerService):
        self.ledger = ledger_service

    async def hold(self, session: AsyncSession, payment: Payment):
        """Phase 1: Reserve funds into PSP suspense account."""
        payment.status = PaymentStatus.PROCESSING
        session.add(payment)
        await session.flush()

        postings = [
            Posting(account_id=payment.payer_account, direction=Direction.DEBIT, amount=payment.amount),
            Posting(account_id=PSP_SUSPENSE_ACCOUNT_ID, direction=Direction.CREDIT, amount=payment.amount),
        ]
        await self.ledger.post(session, TransactionType.PAYMENT, payment.id, postings)

        # Atomic Outbox record
        outbox_event = Outbox(
            aggregate_type="payment",
            aggregate_id=payment.id,
            event_type="payment.processing",
            payload={
                "paymentId": str(payment.id),
                "merchantId": payment.merchant_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status.value,
            },
        )
        session.add(outbox_event)
        await session.flush()

    async def settle(self, session: AsyncSession, payment_id: uuid.UUID, psp_reference: str) -> Payment:
        """Phase 3a: Settle funds to merchant payee upon PSP success."""
        stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
        res = await session.execute(stmt)
        payment = res.scalar_one_or_none()
        if not payment:
            raise PaymentNotFoundException(payment_id)

        payment.status = PaymentStatus.SUCCEEDED
        payment.psp_reference = psp_reference
        payment.version += 1
        payment.updated_at = datetime.now(timezone.utc)

        postings = [
            Posting(account_id=PSP_SUSPENSE_ACCOUNT_ID, direction=Direction.DEBIT, amount=payment.amount),
            Posting(account_id=payment.payee_account, direction=Direction.CREDIT, amount=payment.amount),
        ]
        await self.ledger.post(session, TransactionType.PAYMENT, payment.id, postings)

        outbox_event = Outbox(
            aggregate_type="payment",
            aggregate_id=payment.id,
            event_type="payment.succeeded",
            payload={
                "paymentId": str(payment.id),
                "merchantId": payment.merchant_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status.value,
                "pspReference": payment.psp_reference,
            },
        )
        session.add(outbox_event)
        await session.flush()
        return payment

    async def reverse(self, session: AsyncSession, payment_id: uuid.UUID) -> Payment:
        """Phase 3b: Compensating transaction returning funds to payer upon PSP decline."""
        stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
        res = await session.execute(stmt)
        payment = res.scalar_one_or_none()
        if not payment:
            raise PaymentNotFoundException(payment_id)

        payment.status = PaymentStatus.FAILED
        payment.version += 1
        payment.updated_at = datetime.now(timezone.utc)

        postings = [
            Posting(account_id=PSP_SUSPENSE_ACCOUNT_ID, direction=Direction.DEBIT, amount=payment.amount),
            Posting(account_id=payment.payer_account, direction=Direction.CREDIT, amount=payment.amount),
        ]
        await self.ledger.post(session, TransactionType.REVERSAL, payment.id, postings)

        outbox_event = Outbox(
            aggregate_type="payment",
            aggregate_id=payment.id,
            event_type="payment.failed",
            payload={
                "paymentId": str(payment.id),
                "merchantId": payment.merchant_id,
                "amount": payment.amount,
                "status": payment.status.value,
            },
        )
        session.add(outbox_event)
        await session.flush()
        return payment
