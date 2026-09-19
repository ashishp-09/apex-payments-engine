from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_webhook_service
from app.application.webhook_service import WebhookService
from app.infrastructure.database import get_db

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


@router.post(
    "/psp",
    status_code=status.HTTP_200_OK,
    summary="Receive generic HMAC-signed PSP webhooks",
)
@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Receive Stripe signed webhooks",
)
async def handle_webhook(
    request: Request,
    x_psp_signature: Optional[str] = Header(None, alias="X-PSP-Signature"),
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    webhook_service: WebhookService = Depends(get_webhook_service),
    db: AsyncSession = Depends(get_db),
):
    raw_body_bytes = await request.body()
    raw_body = raw_body_bytes.decode("utf-8")
    signature = stripe_signature or x_psp_signature or ""

    async with db.begin():
        await webhook_service.handle(db, raw_body, signature)

    return {"status": "ok"}
