import hashlib
import hmac
import json
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ledger_service import LedgerService
from app.application.payment_saga import PaymentSaga
from app.application.webhook_service import WebhookService
from app.config import settings
from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidSignatureException
from app.domain.models import AccountBalance, Payment, WebhookEvent


@pytest.mark.asyncio
async def test_webhook_signature_and_capture(db_session: AsyncSession, seed_accounts: dict):
    ledger = LedgerService()
    saga = PaymentSaga(ledger)
    webhook_service = WebhookService(saga)

    # 1. Create AUTHORIZED payment
    payment_id = uuid.uuid4()
    psp_ref = f"psp_async_{uuid.uuid4().hex[:8]}"
    payment = Payment(
        id=payment_id,
        merchant_id="merchant_test",
        payer_account=seed_accounts["payer_id"],
        payee_account=seed_accounts["payee_id"],
        amount=5000,
        currency="INR",
        status=PaymentStatus.AUTHORIZED,
        psp_reference=psp_ref,
    )
    db_session.add(payment)
    await db_session.commit()

    # 2. Construct HMAC-signed Webhook Payload
    payload = {
        "pspEventId": f"evt_{uuid.uuid4().hex}",
        "type": "payment.captured",
        "pspReference": psp_ref,
    }
    raw_body = json.dumps(payload)
    signature = hmac.new(
        settings.PSP_WEBHOOK_SECRET.encode("utf-8"),
        raw_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # 3. Handle Webhook
    await webhook_service.handle(db_session, raw_body, signature)
    await db_session.commit()

    # 4. Verify Payment Transitioned to SUCCEEDED
    updated_payment = await db_session.get(Payment, payment_id)
    assert updated_payment.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_webhook_tampered_signature_rejected(db_session: AsyncSession):
    ledger = LedgerService()
    saga = PaymentSaga(ledger)
    webhook_service = WebhookService(saga)

    raw_body = json.dumps({"pspEventId": "evt_123", "type": "payment.captured"})
    invalid_signature = "invalid_tampered_signature_12345"

    with pytest.raises(InvalidSignatureException):
        await webhook_service.handle(db_session, raw_body, invalid_signature)
