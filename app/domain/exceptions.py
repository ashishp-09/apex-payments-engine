from uuid import UUID


class DomainException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InsufficientFundsException(DomainException):
    def __init__(self, account_id: UUID, current_balance: int, required_amount: int):
        super().__init__(
            f"Insufficient funds for account {account_id}: balance={current_balance}, required={required_amount}",
            status_code=422,
        )
        self.account_id = account_id
        self.current_balance = current_balance
        self.required_amount = required_amount


class AccountNotFoundException(DomainException):
    def __init__(self, account_id: UUID):
        super().__init__(f"Account not found: {account_id}", status_code=404)
        self.account_id = account_id


class PaymentNotFoundException(DomainException):
    def __init__(self, payment_id: UUID):
        super().__init__(f"Payment not found: {payment_id}", status_code=404)
        self.payment_id = payment_id


class IdempotencyConflictException(DomainException):
    def __init__(self, key: str):
        super().__init__(f"Concurrent request in progress for idempotency key: {key}", status_code=409)
        self.key = key


class IdempotencyMismatchException(DomainException):
    def __init__(self, key: str):
        super().__init__(f"Idempotency key '{key}' was previously used with a different request payload", status_code=422)
        self.key = key


class InvalidSignatureException(DomainException):
    def __init__(self):
        super().__init__("Invalid webhook signature", status_code=401)


class RefundNotAllowedException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class LedgerImbalanceException(DomainException):
    def __init__(self, net_amount: int):
        super().__init__(f"Ledger entries are unbalanced (net = {net_amount}). Sum of signed amounts must be zero.", status_code=500)
        self.net_amount = net_amount
