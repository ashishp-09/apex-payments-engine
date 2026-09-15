from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from app.domain.enums import AuthorizationOutcome
from app.domain.models import Payment


@dataclass
class AuthorizationResult:
    outcome: AuthorizationOutcome
    psp_reference: Optional[str] = None
    decline_reason: Optional[str] = None

    @classmethod
    def captured(cls, psp_reference: str) -> "AuthorizationResult":
        return cls(outcome=AuthorizationOutcome.CAPTURED, psp_reference=psp_reference)

    @classmethod
    def pending(cls, psp_reference: str) -> "AuthorizationResult":
        return cls(outcome=AuthorizationOutcome.PENDING, psp_reference=psp_reference)

    @classmethod
    def declined(cls, reason: str) -> "AuthorizationResult":
        return cls(outcome=AuthorizationOutcome.DECLINED, decline_reason=reason)


class PaymentProvider(ABC):
    @abstractmethod
    async def authorize(self, payment: Payment) -> AuthorizationResult:
        """Invokes external payment provider to authorize/capture funds."""
        pass
