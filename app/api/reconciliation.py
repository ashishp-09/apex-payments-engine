from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_reconciliation_service
from app.application.reconciliation_service import ReconciliationService
from app.application.schemas import IntegrityResponse
from app.infrastructure.database import get_db

router = APIRouter(prefix="/v1/reconciliation", tags=["Reconciliation"])


@router.get(
    "/report",
    response_model=IntegrityResponse,
    summary="Read-only ledger mathematical integrity report",
)
async def get_integrity_report(
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
    db: AsyncSession = Depends(get_db),
):
    return await reconciliation_service.audit_integrity(db)
