from enum import Enum


class OwnerType(str, Enum):
    USER = "USER"
    MERCHANT = "MERCHANT"
    SYSTEM = "SYSTEM"


class AccountType(str, Enum):
    USER_WALLET = "USER_WALLET"
    MERCHANT_PAYABLE = "MERCHANT_PAYABLE"
    PSP_SUSPENSE = "PSP_SUSPENSE"
    FEE_INCOME = "FEE_INCOME"


class Direction(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TransactionType(str, Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"
    FEE = "FEE"


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    AUTHORIZED = "AUTHORIZED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    FUNDS_LOCKED = "FUNDS_LOCKED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class RefundStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class WebhookStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class AuthorizationOutcome(str, Enum):
    CAPTURED = "CAPTURED"
    PENDING = "PENDING"
    DECLINED = "DECLINED"
