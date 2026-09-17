import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.payment_saga import PaymentSaga
from app.domain.enums import PaymentStatus, WebhookStatus
from app.domain.exceptions import InvalidSignatureException
from app.domain.models import Payment, WebhookEvent
from app.infrastructure.psp.signature import StripeWebhookSignatureVerifier, WebhookSignatureVerifier


class WebhookService:
    def __init__(self, saga: PaymentSaga):
        self.saga = saga

    async def handle(self, session: AsyncSession, raw_body: str, signature: str):
        # 1. Verify Signature (HMAC or Stripe)
        if not signature:
            raise InvalidSignatureException()

        is_valid = WebhookSignatureVerifier.is_valid(
            raw_body, signature
        ) or StripeWebhookSignatureVerifier.is_valid(raw_body, signature)
        if not is_valid:
            raise InvalidSignatureException()

        # 2. Parse Event Payload
        try:
            data = json.loads(raw_body)
        except Exception:
            raise ValueError("Invalid JSON payload")

        if "data" in data and "object" in data["data"]:  # Stripe format
            event_id = data.get("id", str(uuid.uuid4()))
            event_type = data.get("type", "")
            psp_reference = data["data"]["object"].get("id", "")
        else:  # Generic PSP format
            event_id = data.get("pspEventId", data.get("eventId", str(uuid.uuid4())))
            event_type = data.get("type", data.get("eventType", ""))
            psp_reference = data.get("pspReference", "")

        # 3. Deduplication Check on psp_event_id
        stmt = select(WebhookEvent).where(WebhookEvent.psp_event_id == event_id)
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            return  # Idempotent no-op

        # 4. Record Webhook
        webhook_record = WebhookEvent(
            psp_event_id=event_id,
            payload=raw_body,
            status=WebhookStatus.PROCESSED,
            received_at=datetime.now(timezone.utc),
        )
        session.add(webhook_record)
        await session.flush()

        # 5. Transition Payment if in AUTHORIZED state
        if psp_reference:
            stmt = select(Payment).where(Payment.psp_reference == psp_reference).with_for_update()
            res = await session.execute(stmt)
            payment = res.scalar_one_or_none()

            if payment and payment.status == PaymentStatus.AUTHORIZED:
                capture_events = {
                    "payment.captured",
                    "payment_intent.succeeded",
                    "payment_intent.amount_capturable_updated",
                    "charge.captured",
                }
                fail_events = {
                    "payment.failed",
                    "payment_intent.payment_failed",
                    "payment_intent.canceled",
                }

                if event_type in capture_events:
                    await self.saga.settle(session, payment.id, psp_reference)
                elif event_type in fail_events:
                    await self.saga.reverse(session, payment.id)
