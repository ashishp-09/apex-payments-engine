import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.schemas import BalanceResponse, LedgerEntryResponse, LedgerPageResponse
from app.domain.exceptions import AccountNotFoundException
from app.domain.models import Account, AccountBalance, LedgerEntry
from app.infrastructure.database import get_db

router = APIRouter(prefix="/v1/accounts", tags=["Accounts & Ledger"])


@router.get(
    "/{account_id}/balance",
    response_model=BalanceResponse,
    summary="Get current account balance",
)
async def get_balance(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AccountBalance, Account.currency)
        .join(Account, Account.id == AccountBalance.account_id)
        .where(AccountBalance.account_id == account_id)
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        # Check if account exists
        acc_stmt = select(Account).where(Account.id == account_id)
        acc_res = await db.execute(acc_stmt)
        acc = acc_res.scalar_one_or_none()
        if not acc:
            raise AccountNotFoundException(account_id)
        return BalanceResponse(
            accountId=account_id,
            balance=0,
            currency=acc.currency,
            updatedAt=acc.created_at,
        )

    balance_obj, currency = row
    return BalanceResponse(
        accountId=balance_obj.account_id,
        balance=balance_obj.balance,
        currency=currency,
        updatedAt=balance_obj.updated_at,
    )


@router.get(
    "/{account_id}/ledger",
    response_model=LedgerPageResponse,
    summary="Get ledger postings audit trail for account",
)
async def get_ledger_postings(
    account_id: uuid.UUID,
    limit: Optional[int] = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.account_id == account_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    entries = res.scalars().all()

    return LedgerPageResponse(
        accountId=account_id,
        entries=[
            LedgerEntryResponse(
                id=e.id,
                transactionId=e.transaction_id,
                direction=e.direction,
                amount=e.amount,
                createdAt=e.created_at,
            )
            for e in entries
        ],
    )
