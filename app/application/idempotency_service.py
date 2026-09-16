import hashlib
import json
import uuid
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.enums import IdempotencyStatus
from app.domain.exceptions import IdempotencyConflictException, IdempotencyMismatchException
from app.domain.models import IdempotencyRecord
from app.infrastructure.redis_client import IdempotencyLock


class IdempotencyService:
    """
    Two-Tier Idempotency Management:
    1. Fast path: Redis distributed lock.
    2. Durable claim: PostgreSQL unique constraint with full response caching and replay.
    """

    def __init__(self, lock: Optional[IdempotencyLock] = None):
        self.lock = lock

    @staticmethod
    def compute_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def claim_or_replay(
        self,
        session: AsyncSession,
        merchant_id: str,
        idem_key: str,
        payload: dict[str, Any],
    ) -> Optional[tuple[int, dict[str, Any]]]:
        """
        Attempts to claim the idempotency key.
        Returns None if key is fresh and claimed by caller.
        Returns (response_code, response_body) if key was already completed and should be replayed.
        Raises IdempotencyConflictException (409) if concurrent request is in progress.
        Raises IdempotencyMismatchException (422) if key is reused with different payload.
        """
        req_hash = self.compute_hash(payload)

        # 1. Redis fast path check
        if self.lock:
            await self.lock.acquire(merchant_id, idem_key, req_hash)

        # 2. Durable check in PostgreSQL
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.merchant_id == merchant_id,
            IdempotencyRecord.idem_key == idem_key,
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if record is None:
            # First time seeing this key: create claim
            new_record = IdempotencyRecord(
                merchant_id=merchant_id,
                idem_key=idem_key,
                request_hash=req_hash,
                status=IdempotencyStatus.IN_PROGRESS,
            )
            session.add(new_record)
            await session.flush()
            return None

        # Existing record check
        if record.request_hash != req_hash:
            raise IdempotencyMismatchException(idem_key)

        if record.status == IdempotencyStatus.IN_PROGRESS:
            raise IdempotencyConflictException(idem_key)

        if record.status == IdempotencyStatus.COMPLETED:
            # Replay stored response
            return record.response_code or 200, record.response_body or {}

        return None

    async def complete(
        self,
        session: AsyncSession,
        merchant_id: str,
        idem_key: str,
        resource_id: uuid.UUID,
        response_code: int,
        response_body: dict[str, Any],
    ):
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.merchant_id == merchant_id,
            IdempotencyRecord.idem_key == idem_key,
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            record.status = IdempotencyStatus.COMPLETED
            record.resource_id = resource_id
            record.response_code = response_code
            record.response_body = response_body
            await session.flush()
