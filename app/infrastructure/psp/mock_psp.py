import uuid
from app.domain.models import Payment
from app.infrastructure.psp.provider import AuthorizationResult, PaymentProvider


class MockPspClient(PaymentProvider):
    """
    In-memory Mock Payment Provider simulating synchronous capture, async authorization, and declines.
    """

    async def authorize(self, payment: Payment) -> AuthorizationResult:
        # Simulate business rules based on amount
        if payment.amount == 40001:  # Magic value for decline testing
            return AuthorizationResult.declined("Card declined by mock bank")
        elif payment.amount == 40002:  # Magic value for async webhook testing
            return AuthorizationResult.pending(f"mock_async_ref_{uuid.uuid4().hex[:12]}")
        else:
            return AuthorizationResult.captured(f"mock_psp_ref_{uuid.uuid4().hex[:12]}")
