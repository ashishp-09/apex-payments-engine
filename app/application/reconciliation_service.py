from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.payment_saga import PaymentSaga
from app.application.schemas import IntegrityResponse
from app.domain.enums import Direction, PaymentStatus
from app.domain.models import AccountBalance, LedgerEntry, Payment


class ReconciliationService:
    def __init__(self, saga: PaymentSaga):
        self.saga = saga

    async def audit_integrity(self, session: AsyncSession) -> IntegrityResponse:
        """
        Global mathematical audit:
        1. Asserts sum(DEBITS) - sum(CREDITS) == 0 across all historical entries.
        2. Detects if any materialized balance differs from historical sum of postings.
        """
        # 1. Global Ledger Net Check
        signed_amount = case((LedgerEntry.direction == Direction.DEBIT, LedgerEntry.amount), else_=-LedgerEntry.amount)
        stmt = select(func.coalesce(func.sum(signed_amount), 0))
        res = await session.execute(stmt)
        ledger_net = res.scalar_one()

        # 2. Account-Level Drift Check
        # Calculate calculated balance from postings
        calc_amount = case((LedgerEntry.direction == Direction.CREDIT, LedgerEntry.amount), else_=-LedgerEntry.amount)
        postings_subq = (
            select(LedgerEntry.account_id, func.sum(calc_amount).label("computed_balance"))
            .group_by(LedgerEntry.account_id)
            .subquery()
        )

        drift_stmt = (
            select(AccountBalance.account_id)
            .outerjoin(postings_subq, AccountBalance.account_id == postings_subq.c.account_id)
            .where(AccountBalance.balance != func.coalesce(postings_subq.c.computed_balance, 0))
        )
        drift_res = await session.execute(drift_stmt)
        drifted_accounts = drift_res.scalars().all()

        balanced = (ledger_net == 0) and (len(drifted_accounts) == 0)
        return IntegrityResponse(
            balanced=balanced,
            ledgerNet=ledger_net,
            driftedAccountsCount=len(drifted_accounts),
        )

    async def expire_stale_holds(self, session: AsyncSession, timeout_minutes: int = 30) -> int:
        """Finds abandoned holds in AUTHORIZED state older than timeout and reverses them."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stmt = (
            select(Payment)
            .where(
                Payment.status == PaymentStatus.AUTHORIZED,
                Payment.created_at < cutoff,
            )
            .with_for_update()
        )
        res = await session.execute(stmt)
        stale_payments = res.scalars().all()

        count = 0
        for p in stale_payments:
            await self.saga.reverse(session, p.id)
            count += 1

        return count
