import asyncio
import os
import uuid
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.domain.enums import AccountType, OwnerType
from app.domain.models import Account, AccountBalance, Base
from app.infrastructure.database import get_db
from app.infrastructure.redis_client import IdempotencyLock, get_redis_client
from app.main import app

# Use SQLite memory or PostgreSQL connection for tests
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_accounts(db_session: AsyncSession):
    """Seed sample accounts and system accounts."""
    psp_suspense_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    fee_income_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    payer_acc_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    payee_acc_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")

    # Add system accounts
    suspense = Account(id=psp_suspense_id, owner_type=OwnerType.SYSTEM, owner_id="psp", type=AccountType.PSP_SUSPENSE, currency="INR")
    suspense_bal = AccountBalance(account_id=psp_suspense_id, balance=0, version=0)
    fee = Account(id=fee_income_id, owner_type=OwnerType.SYSTEM, owner_id="fees", type=AccountType.FEE_INCOME, currency="INR")
    fee_bal = AccountBalance(account_id=fee_income_id, balance=0, version=0)

    # Add User Accounts
    payer = Account(id=payer_acc_id, owner_type=OwnerType.USER, owner_id="user_1", type=AccountType.USER_WALLET, currency="INR")
    payer_bal = AccountBalance(account_id=payer_acc_id, balance=100000, version=0)  # 1000.00 INR
    payee = Account(id=payee_acc_id, owner_type=OwnerType.MERCHANT, owner_id="merchant_1", type=AccountType.MERCHANT_PAYABLE, currency="INR")
    payee_bal = AccountBalance(account_id=payee_acc_id, balance=0, version=0)

    db_session.add_all([suspense, suspense_bal, fee, fee_bal, payer, payer_bal, payee, payee_bal])
    await db_session.commit()

    return {
        "payer_id": payer_acc_id,
        "payee_id": payee_acc_id,
        "suspense_id": psp_suspense_id,
        "fee_id": fee_income_id,
    }
