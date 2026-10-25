from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://omnihub:omnihub@postgres:5432/omnihub"
    redis_url: str = "redis://redis:6379"
    app_env: str = "development"
    debug: bool = False


settings = Settings()
