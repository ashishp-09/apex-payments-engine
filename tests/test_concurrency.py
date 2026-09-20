import asyncio
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ledger_service import LedgerService, Posting
from app.domain.enums import Direction, TransactionType
from app.domain.exceptions import InsufficientFundsException
from app.domain.models import AccountBalance
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_concurrent_debits_prevent_oversell(seed_accounts: dict):
    """
    Spawns 20 concurrent transactions attempting to debit 10,000 each
    from an initial balance of 100,000. Exactly 10 must succeed,
    and 10 must fail with InsufficientFundsException. Balance must never drop below 0.
    """
    ledger = LedgerService()
    payer_id = seed_accounts["payer_id"]
    payee_id = seed_accounts["payee_id"]
    debit_amount = 10000

    success_count = 0
    failure_count = 0

    async def attempt_debit():
        nonlocal success_count, failure_count
        async with TestingSessionLocal() as session:
            async with session.begin():
                postings = [
                    Posting(account_id=payer_id, direction=Direction.DEBIT, amount=debit_amount),
                    Posting(account_id=payee_id, direction=Direction.CREDIT, amount=debit_amount),
                ]
                try:
                    await ledger.post(session, TransactionType.PAYMENT, uuid.uuid4(), postings)
                    success_count += 1
                except InsufficientFundsException:
                    failure_count += 1

    # Run 20 concurrent debit requests
    await asyncio.gather(*[attempt_debit() for _ in range(20)])

    assert success_count == 10
    assert failure_count == 10

    async with TestingSessionLocal() as session:
        bal = await session.get(AccountBalance, payer_id)
        assert bal.balance == 0
