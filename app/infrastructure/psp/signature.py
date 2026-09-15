import hashlib
import hmac
import logging
import stripe
from app.config import settings

logger = logging.getLogger(__name__)


class WebhookSignatureVerifier:
    """Verifies HMAC-SHA256 signatures for generic PSP webhooks."""

    @staticmethod
    def is_valid(raw_payload: str, signature_header: str) -> bool:
        if not raw_payload or not signature_header:
            return False

        secret = settings.PSP_WEBHOOK_SECRET
        if not secret:
            return False

        computed = hmac.new(
            secret.encode("utf-8"),
            raw_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed, signature_header)


class StripeWebhookSignatureVerifier:
    """Verifies Stripe-Signature headers with tolerance window."""

    @staticmethod
    def is_valid(raw_payload: str, signature_header: str) -> bool:
        if not raw_payload or not signature_header:
            return False

        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            return False

        try:
            stripe.Webhook.construct_event(
                payload=raw_payload,
                sig_header=signature_header,
                secret=secret,
                tolerance=300,  # 5 minutes
            )
            return True
        except Exception as e:
            logger.warning(f"Stripe signature verification failed: {e}")
            return False
