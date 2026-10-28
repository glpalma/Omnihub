from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://omnihub:omnihub@postgres:5432/omnihub"
    redis_url: str = "redis://redis:6379"
    app_env: str = "development"
    debug: bool = False

    featherless_api_key: str = ""
    featherless_model: str = "deepseek-ai/DeepSeek-V4.1-Flash-1017"

    # WhatsApp Cloud API — usado pelo WhatsAppSenderService (slice 03)
    wa_phone_number_id: str = ""
    wa_token: str = ""

    # Comportamento do bot
    bot_max_turns: int = 10  # força escalação após N turnos de ida-e-volta


settings = Settings()
