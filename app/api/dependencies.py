from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.idempotency_service import IdempotencyService
from app.application.ledger_service import LedgerService
from app.application.payment_saga import PaymentSaga
from app.application.payment_service import PaymentService
from app.application.reconciliation_service import ReconciliationService
from app.application.refund_service import RefundService
from app.application.webhook_service import WebhookService
from app.config import settings
from app.infrastructure.database import AsyncSessionLocal, get_db
from app.infrastructure.psp.mock_psp import MockPspClient
from app.infrastructure.psp.provider import PaymentProvider
from app.infrastructure.psp.stripe_psp import StripePaymentProvider
from app.infrastructure.redis_client import IdempotencyLock, get_redis_client


def get_payment_provider() -> PaymentProvider:
    if settings.PSP_PROVIDER.lower() == "stripe":
        return StripePaymentProvider()
    return MockPspClient()


def get_ledger_service() -> LedgerService:
    return LedgerService()


async def get_idempotency_service(
    redis=Depends(get_redis_client),
) -> IdempotencyService:
    lock = IdempotencyLock(redis)
    return IdempotencyService(lock=lock)


def get_payment_saga(
    ledger: LedgerService = Depends(get_ledger_service),
) -> PaymentSaga:
    return PaymentSaga(ledger_service=ledger)


def get_payment_service(
    saga: PaymentSaga = Depends(get_payment_saga),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    psp: PaymentProvider = Depends(get_payment_provider),
) -> PaymentService:
    return PaymentService(
        saga=saga,
        idempotency=idempotency,
        psp=psp,
        session_factory=AsyncSessionLocal,
    )


def get_refund_service(
    ledger: LedgerService = Depends(get_ledger_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
) -> RefundService:
    return RefundService(ledger_service=ledger, idempotency_service=idempotency)


def get_webhook_service(
    saga: PaymentSaga = Depends(get_payment_saga),
) -> WebhookService:
    return WebhookService(saga=saga)


def get_reconciliation_service(
    saga: PaymentSaga = Depends(get_payment_saga),
) -> ReconciliationService:
    return ReconciliationService(saga=saga)
