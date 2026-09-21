import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.idempotency_service import IdempotencyService
from app.application.ledger_service import LedgerService
from app.application.payment_saga import PaymentSaga
from app.application.payment_service import PaymentService
from app.application.schemas import CreatePaymentRequest
from app.domain.enums import PaymentStatus
from app.domain.models import AccountBalance, Payment
from app.infrastructure.psp.mock_psp import MockPspClient


@pytest.mark.asyncio
async def test_create_payment_success(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    saga = PaymentSaga(ledger)
    idempotency = IdempotencyService()
    psp = MockPspClient()
    session_factory = lambda: db_session

    service = PaymentService(saga, idempotency, psp, session_factory)

    request = CreatePaymentRequest(
        merchantId="merchant_test",
        payerAccountId=seed_accounts["payer_id"],
        payeeAccountId=seed_accounts["payee_id"],
        amount=5000,
        currency="INR",
    )

    idem_key = f"key_{uuid.uuid4()}"
    status_code, response = await service.create(idem_key, request)

    assert status_code == 201
    assert response.status == PaymentStatus.SUCCEEDED
    assert response.amount == 5000

    # Verify balances
    payer_bal = await db_session.get(AccountBalance, seed_accounts["payer_id"])
    payee_bal = await db_session.get(AccountBalance, seed_accounts["payee_id"])
    assert payer_bal.balance == 95000
    assert payee_bal.balance == 5000


@pytest.mark.asyncio
async def test_payment_decline_and_reversal(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    saga = PaymentSaga(ledger)
    idempotency = IdempotencyService()
    psp = MockPspClient()
    session_factory = lambda: db_session

    service = PaymentService(saga, idempotency, psp, session_factory)

    # Amount 40001 triggers Mock PSP decline
    request = CreatePaymentRequest(
        merchantId="merchant_test",
        payerAccountId=seed_accounts["payer_id"],
        payeeAccountId=seed_accounts["payee_id"],
        amount=40001,
        currency="INR",
    )

    idem_key = f"key_{uuid.uuid4()}"
    status_code, response = await service.create(idem_key, request)

    assert status_code == 201
    assert response.status == PaymentStatus.FAILED

    # Payer balance should be restored to initial 100,000 via compensating transaction
    payer_bal = await db_session.get(AccountBalance, seed_accounts["payer_id"])
    payee_bal = await db_session.get(AccountBalance, seed_accounts["payee_id"])
    assert payer_bal.balance == 100000
    assert payee_bal.balance == 0
