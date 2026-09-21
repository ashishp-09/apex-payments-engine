import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.idempotency_service import IdempotencyService
from app.application.ledger_service import LedgerService, Posting
from app.application.payment_saga import PaymentSaga
from app.application.refund_service import RefundService
from app.domain.enums import Direction, PaymentStatus, RefundStatus, TransactionType
from app.domain.exceptions import RefundNotAllowedException
from app.domain.models import AccountBalance, Payment


@pytest.mark.asyncio
async def test_full_refund_success(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    idempotency = IdempotencyService()
    refund_service = RefundService(ledger, idempotency)

    # 1. Create Succeeded Payment
    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        merchant_id="merchant_test",
        payer_account=seed_accounts["payer_id"],
        payee_account=seed_accounts["payee_id"],
        amount=5000,
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
    )
    db_session.add(payment)

    # Set balances as post-payment: payer=95000, payee=5000
    payer_bal = await db_session.get(AccountBalance, seed_accounts["payer_id"])
    payee_bal = await db_session.get(AccountBalance, seed_accounts["payee_id"])
    payer_bal.balance = 95000
    payee_bal.balance = 5000
    await db_session.commit()

    # 2. Process Full Refund
    idem_key = f"refund_{uuid.uuid4()}"
    status_code, response = await refund_service.refund(db_session, idem_key, payment_id, 5000)

    assert status_code == 201
    assert response.status == RefundStatus.SUCCEEDED
    assert response.amount == 5000

    # 3. Verify Payment Status & Balances
    updated_payment = await db_session.get(Payment, payment_id)
    assert updated_payment.status == PaymentStatus.REFUNDED
    assert updated_payment.refunded_amount == 5000

    assert payer_bal.balance == 100000
    assert payee_bal.balance == 0


@pytest.mark.asyncio
async def test_over_refund_rejected(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    idempotency = IdempotencyService()
    refund_service = RefundService(ledger, idempotency)

    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        merchant_id="merchant_test",
        payer_account=seed_accounts["payer_id"],
        payee_account=seed_accounts["payee_id"],
        amount=5000,
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
        refunded_amount=4000,
    )
    db_session.add(payment)
    await db_session.commit()

    # Attempting to refund 2000 when only 1000 is left -> raises 422
    with pytest.raises(RefundNotAllowedException):
        await refund_service.refund(db_session, f"key_{uuid.uuid4()}", payment_id, 2000)
