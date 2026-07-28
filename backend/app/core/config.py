from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://oa:oa@localhost:5432/oa"
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    SEED_ADMIN_EMAIL: str = "admin@company.com"
    SEED_ADMIN_PASSWORD: str = "Admin123!"
    EXPENSE_L2_THRESHOLD: Decimal = 2000
    UPLOAD_DIR: str = "uploads"


settings = Settings()
