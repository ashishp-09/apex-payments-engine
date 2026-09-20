import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ledger_service import LedgerService, Posting
from app.domain.enums import Direction, TransactionType
from app.domain.exceptions import InsufficientFundsException, LedgerImbalanceException
from app.domain.models import AccountBalance, LedgerEntry, LedgerTransaction


@pytest.mark.asyncio
async def test_ledger_post_balanced_transaction(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    payer_id = seed_accounts["payer_id"]
    payee_id = seed_accounts["payee_id"]

    postings = [
        Posting(account_id=payer_id, direction=Direction.DEBIT, amount=5000),
        Posting(account_id=payee_id, direction=Direction.CREDIT, amount=5000),
    ]

    ref_id = uuid.uuid4()
    txn = await ledger.post(db_session, TransactionType.PAYMENT, ref_id, postings)
    await db_session.commit()

    assert txn.id is not None
    assert txn.type == TransactionType.PAYMENT

    # Check updated balances
    payer_bal = await db_session.get(AccountBalance, payer_id)
    payee_bal = await db_session.get(AccountBalance, payee_id)
    assert payer_bal.balance == 95000
    assert payee_bal.balance == 5000


@pytest.mark.asyncio
async def test_ledger_rejects_unbalanced_transaction(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    payer_id = seed_accounts["payer_id"]
    payee_id = seed_accounts["payee_id"]

    # Imbalanced: Debit 5000, Credit 4000
    postings = [
        Posting(account_id=payer_id, direction=Direction.DEBIT, amount=5000),
        Posting(account_id=payee_id, direction=Direction.CREDIT, amount=4000),
    ]

    with pytest.raises(LedgerImbalanceException):
        await ledger.post(db_session, TransactionType.PAYMENT, uuid.uuid4(), postings)


@pytest.mark.asyncio
async def test_ledger_rejects_insufficient_funds(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    payer_id = seed_accounts["payer_id"]
    payee_id = seed_accounts["payee_id"]

    # Overdraft attempt: Payer only has 100,000, attempting to debit 200,000
    postings = [
        Posting(account_id=payer_id, direction=Direction.DEBIT, amount=200000),
        Posting(account_id=payee_id, direction=Direction.CREDIT, amount=200000),
    ]

    with pytest.raises(InsufficientFundsException):
        await ledger.post(db_session, TransactionType.PAYMENT, uuid.uuid4(), postings)
