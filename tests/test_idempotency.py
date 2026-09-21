import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.idempotency_service import IdempotencyService
from app.domain.exceptions import IdempotencyConflictException, IdempotencyMismatchException


@pytest.mark.asyncio
async def test_idempotency_claim_and_replay(db_session: AsyncSession):
    service = IdempotencyService(lock=None)
    merchant_id = "test_merchant"
    idem_key = f"key_{uuid.uuid4()}"
    payload = {"amount": 5000, "currency": "INR"}

    # 1. First claim
    res1 = await service.claim_or_replay(db_session, merchant_id, idem_key, payload)
    assert res1 is None  # Claimed successfully

    # 2. Complete with cached response
    resource_id = uuid.uuid4()
    cached_body = {"id": str(resource_id), "status": "SUCCEEDED", "amount": 5000}
    await service.complete(db_session, merchant_id, idem_key, resource_id, 201, cached_body)
    await db_session.commit()

    # 3. Subsequent replay with same key and same payload
    res2 = await service.claim_or_replay(db_session, merchant_id, idem_key, payload)
    assert res2 is not None
    code, body = res2
    assert code == 201
    assert body["status"] == "SUCCEEDED"
    assert body["id"] == str(resource_id)


@pytest.mark.asyncio
async def test_idempotency_rejects_payload_mutation(db_session: AsyncSession):
    service = IdempotencyService(lock=None)
    merchant_id = "test_merchant"
    idem_key = f"key_{uuid.uuid4()}"

    payload1 = {"amount": 5000, "currency": "INR"}
    await service.claim_or_replay(db_session, merchant_id, idem_key, payload1)
    await service.complete(db_session, merchant_id, idem_key, uuid.uuid4(), 201, {})
    await db_session.commit()

    # Mutated payload with same key -> raises 422 mismatch
    payload2 = {"amount": 9999, "currency": "INR"}
    with pytest.raises(IdempotencyMismatchException):
        await service.claim_or_replay(db_session, merchant_id, idem_key, payload2)
