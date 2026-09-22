import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ledger_service import LedgerService, Posting
from app.application.payment_saga import PaymentSaga
from app.application.reconciliation_service import ReconciliationService
from app.domain.enums import Direction, TransactionType


@pytest.mark.asyncio
async def test_reconciliation_audit_integrity(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    saga = PaymentSaga(ledger)
    reconciliation = ReconciliationService(saga)

    # 1. Initially balanced
    report1 = await reconciliation.audit_integrity(db_session)
    assert report1.balanced is True
    assert report1.ledgerNet == 0
    assert report1.driftedAccountsCount == 0

    # 2. Execute balanced transfer
    postings = [
        Posting(account_id=seed_accounts["payer_id"], direction=Direction.DEBIT, amount=10000),
        Posting(account_id=seed_accounts["payee_id"], direction=Direction.CREDIT, amount=10000),
    ]
    await ledger.post(db_session, TransactionType.PAYMENT, uuid.uuid4(), postings)
    await db_session.commit()

    report2 = await reconciliation.audit_integrity(db_session)
    assert report2.balanced is True
    assert report2.ledgerNet == 0
    assert report2.driftedAccountsCount == 0
