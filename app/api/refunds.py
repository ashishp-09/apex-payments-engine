import uuid
from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_refund_service
from app.application.refund_service import RefundService
from app.application.schemas import RefundRequest, RefundResponse
from app.infrastructure.database import get_db

router = APIRouter(prefix="/v1/payments", tags=["Refunds"])


@router.post(
    "/{payment_id}/refunds",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process a full or partial refund",
)
async def process_refund(
    payment_id: uuid.UUID,
    request: RefundRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    refund_service: RefundService = Depends(get_refund_service),
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        status_code, refund_res = await refund_service.refund(
            db, idempotency_key, payment_id, request.amount
        )
    response.status_code = status_code
    return refund_res
