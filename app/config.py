import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "apex-payments-engine"
    APP_ENV: str = "development"
    PORT: int = 8080
    HOST: str = "0.0.0.0"

    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "payments"
    DB_USER: str = "payments"
    DB_PASSWORD: str = "payments"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # PSP / Stripe
    PSP_PROVIDER: str = "stripe"  # "stripe" or "mock"
    PSP_WEBHOOK_SECRET: str = "dev-webhook-secret"
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = "whsec_dev"

    # Background workers
    OUTBOX_RELAY_INTERVAL_MS: int = 1000
    RECONCILIATION_INTERVAL_MS: int = 60000
    AUTHORIZED_HOLD_TIMEOUT_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
