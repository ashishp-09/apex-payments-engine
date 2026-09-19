import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from app.api import accounts_router, payments_router, reconciliation_router, refunds_router, webhooks_router
from app.application.outbox_relay import OutboxRelay
from app.config import settings
from app.domain.exceptions import DomainException
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.redis_client import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("apex-payments-engine")

outbox_relay = OutboxRelay(session_factory=AsyncSessionLocal)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Apex Payments Engine...")
    relay_task = asyncio.create_task(
        outbox_relay.run_loop(poll_interval_seconds=settings.OUTBOX_RELAY_INTERVAL_MS / 1000.0)
    )
    yield
    logger.info("Shutting down Apex Payments Engine...")
    outbox_relay.stop()
    relay_task.cancel()
    try:
        await relay_task
    except asyncio.CancelledError:
        pass
    await close_redis()


app = FastAPI(
    title="Apex Payments & Double-Entry Ledger Engine",
    description="Enterprise-grade distributed financial transaction engine and double-entry wallet ledger.",
    version="1.0.0",
    lifespan=lifespan,
)

# Prometheus Observability Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/actuator/prometheus")


# Global Domain Exception Handler
@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "type": exc.__class__.__name__},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Request validation failed", "details": exc.errors()},
    )


# Health & Probes
@app.get("/actuator/health", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "UP", "service": settings.APP_NAME}


# Mount Routers
app.include_router(payments_router)
app.include_router(accounts_router)
app.include_router(refunds_router)
app.include_router(webhooks_router)
app.include_router(reconciliation_router)
