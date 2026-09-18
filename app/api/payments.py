import uuid
from fastapi import APIRouter, Depends, Header, Response, status
from app.api.dependencies import get_payment_service
from app.application.payment_service import PaymentService
from app.application.schemas import CreatePaymentRequest, PaymentResponse

router = APIRouter(prefix="/v1/payments", tags=["Payments"])


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and process a payment",
)
async def create_payment(
    request: CreatePaymentRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    payment_service: PaymentService = Depends(get_payment_service),
):
    status_code, payment_res = await payment_service.create(idempotency_key, request)
    response.status_code = status_code
    return payment_res


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details",
)
async def get_payment(
    payment_id: uuid.UUID,
    payment_service: PaymentService = Depends(get_payment_service),
):
    return await payment_service.get_payment(payment_id)
