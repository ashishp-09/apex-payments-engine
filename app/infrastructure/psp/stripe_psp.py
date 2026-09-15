import logging
import uuid
import stripe
from app.config import settings
from app.domain.models import Payment
from app.infrastructure.psp.provider import AuthorizationResult, PaymentProvider

logger = logging.getLogger(__name__)


class StripePaymentProvider(PaymentProvider):
    """
    Production integration with Stripe's PaymentIntents API using manual capture.
    """

    def __init__(self):
        if settings.STRIPE_API_KEY:
            stripe.api_key = settings.STRIPE_API_KEY

    async def authorize(self, payment: Payment) -> AuthorizationResult:
        if not settings.STRIPE_API_KEY:
            logger.warning(f"Stripe API key is not configured. Falling back to mock auth for payment {payment.id}")
            return AuthorizationResult.captured(f"stripe_mock_{uuid.uuid4().hex[:12]}")

        try:
            intent = stripe.PaymentIntent.create(
                amount=payment.amount,
                currency=payment.currency.lower(),
                capture_method="manual",
                metadata={
                    "payment_id": str(payment.id),
                    "merchant_id": payment.merchant_id,
                    "payer_account": str(payment.payer_account),
                    "payee_account": str(payment.payee_account),
                },
                idempotency_key=str(payment.id),
            )
            return self._map_stripe_status(intent)

        except stripe.error.CardError as e:
            logger.warning(f"Stripe card declined for payment {payment.id}: {e.user_message}")
            return AuthorizationResult.declined(e.user_message or "Card declined")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error for payment {payment.id}: {e.user_message}", exc_info=True)
            raise RuntimeError(f"Stripe gateway error: {e.user_message}")

    def _map_stripe_status(self, intent: stripe.PaymentIntent) -> AuthorizationResult:
        status = intent.status
        if status in ("succeeded", "requires_capture"):
            return AuthorizationResult.captured(intent.id)
        elif status in ("requires_action", "requires_confirmation", "processing"):
            return AuthorizationResult.pending(intent.id)
        elif status in ("requires_payment_method", "canceled"):
            reason = (
                intent.last_payment_error.message
                if intent.last_payment_error
                else f"Payment declined by Stripe (status={status})"
            )
            return AuthorizationResult.declined(reason)
        return AuthorizationResult.pending(intent.id)
