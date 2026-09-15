import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.domain.enums import Direction, PaymentStatus, RefundStatus


class CreatePaymentRequest(BaseModel):
    merchantId: str = Field(..., description="Merchant identifier", min_length=1)
    payerAccountId: uuid.UUID = Field(..., description="Payer account UUID")
    payeeAccountId: uuid.UUID = Field(..., description="Payee account UUID")
    amount: int = Field(..., gt=0, description="Amount in minor currency units (e.g. cents/paise)")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 Currency Code")


class PaymentResponse(BaseModel):
    id: uuid.UUID
    merchantId: str
    payerAccountId: uuid.UUID
    payeeAccountId: uuid.UUID
    amount: int
    currency: str
    status: PaymentStatus
    pspReference: Optional[str] = None
    refundedAmount: int = 0
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class RefundRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in minor units to refund")


class RefundResponse(BaseModel):
    id: uuid.UUID
    paymentId: uuid.UUID
    amount: int
    status: RefundStatus
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class BalanceResponse(BaseModel):
    accountId: uuid.UUID
    balance: int
    currency: str
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerEntryResponse(BaseModel):
    id: int
    transactionId: uuid.UUID
    direction: Direction
    amount: int
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerPageResponse(BaseModel):
    accountId: uuid.UUID
    entries: list[LedgerEntryResponse]


class IntegrityResponse(BaseModel):
    balanced: bool
    ledgerNet: int
    driftedAccountsCount: int
