import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.enums import Direction, TransactionType
from app.domain.exceptions import InsufficientFundsException, LedgerImbalanceException
from app.domain.models import Account, AccountBalance, LedgerEntry, LedgerTransaction


@dataclass
class Posting:
    account_id: uuid.UUID
    direction: Direction
    amount: int


class LedgerService:
    """
    Core double-entry bookkeeping engine. Enforces:
    1. Zero-drift invariant (sum of debits == sum of credits).
    2. Pessimistic row locking (SELECT ... FOR UPDATE) on account balances.
    3. Non-negative balance check.
    """

    @staticmethod
    def validate_balanced(postings: list[Posting]):
        if not postings or len(postings) < 2:
            raise LedgerImbalanceException(net_amount=0)

        net = 0
        for p in postings:
            if p.amount <= 0:
                raise ValueError(f"Posting amount must be strictly positive: {p.amount}")
            if p.direction == Direction.DEBIT:
                net += p.amount
            elif p.direction == Direction.CREDIT:
                net -= p.amount

        if net != 0:
            raise LedgerImbalanceException(net_amount=net)

    async def post(
        self,
        session: AsyncSession,
        transaction_type: TransactionType,
        reference_id: uuid.UUID,
        postings: list[Posting],
    ) -> LedgerTransaction:
        self.validate_balanced(postings)

        # 1. Create LedgerTransaction
        txn = LedgerTransaction(
            id=uuid.uuid4(),
            type=transaction_type,
            reference_id=reference_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(txn)
        await session.flush()

        # 2. Sort unique account IDs to prevent deadlocks under concurrent multi-account transactions
        sorted_account_ids = sorted(list(set(p.account_id for p in postings)))

        # 3. Lock account balances under SELECT ... FOR UPDATE
        balances_map: dict[uuid.UUID, AccountBalance] = {}
        for acc_id in sorted_account_ids:
            stmt = select(AccountBalance).where(AccountBalance.account_id == acc_id).with_for_update()
            res = await session.execute(stmt)
            balance_row = res.scalar_one_or_none()
            if balance_row is None:
                # Auto-initialize balance row if not present
                balance_row = AccountBalance(account_id=acc_id, balance=0, version=0)
                session.add(balance_row)
                await session.flush()
            balances_map[acc_id] = balance_row

        # 4. Apply postings and create immutable ledger entry records
        for p in postings:
            entry = LedgerEntry(
                transaction_id=txn.id,
                account_id=p.account_id,
                direction=p.direction,
                amount=p.amount,
                created_at=datetime.now(timezone.utc),
            )
            session.add(entry)

            # Apply to balance cache
            bal = balances_map[p.account_id]
            if p.direction == Direction.DEBIT:
                if bal.balance < p.amount:
                    raise InsufficientFundsException(
                        account_id=p.account_id,
                        current_balance=bal.balance,
                        required_amount=p.amount,
                    )
                bal.balance -= p.amount
            elif p.direction == Direction.CREDIT:
                bal.balance += p.amount

            bal.version += 1
            bal.updated_at = datetime.now(timezone.utc)

        await session.flush()
        return txn
