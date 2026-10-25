from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8080, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    bot_run_mode: Literal["polling", "webhook"] = Field(default="polling", alias="BOT_RUN_MODE")
    bot_drop_pending_updates: bool = Field(default=False, alias="BOT_DROP_PENDING_UPDATES")
    bot_webhook_url: str = Field(default="", alias="BOT_WEBHOOK_URL")
    bot_webhook_path: str = Field(default="/telegram/webhook", alias="BOT_WEBHOOK_PATH")
    bot_webhook_secret: str = Field(default="", alias="BOT_WEBHOOK_SECRET")
    bot_webhook_host: str = Field(default="0.0.0.0", alias="BOT_WEBHOOK_HOST")
    bot_webhook_port: int = Field(default=8081, alias="BOT_WEBHOOK_PORT")
    api_base_url: str = Field(default="http://127.0.0.1:8080", alias="API_BASE_URL")
    api_service_token: str = Field(default="", alias="API_SERVICE_TOKEN")
    api_rate_limit_suggest_per_minute: int = Field(
        default=30,
        alias="API_RATE_LIMIT_SUGGEST_PER_MINUTE",
    )
    api_rate_limit_feedback_per_minute: int = Field(
        default=60,
        alias="API_RATE_LIMIT_FEEDBACK_PER_MINUTE",
    )
    bot_api_max_retries: int = Field(default=2, alias="BOT_API_MAX_RETRIES")
    bot_api_retry_base_ms: int = Field(default=300, alias="BOT_API_RETRY_BASE_MS")
    crm_sync_url: str = Field(default="", alias="CRM_SYNC_URL")
    crm_sync_token: str = Field(default="", alias="CRM_SYNC_TOKEN")
    crm_sync_timeout_ms: int = Field(default=5000, alias="CRM_SYNC_TIMEOUT_MS")
    crm_sync_max_retries: int = Field(default=2, alias="CRM_SYNC_MAX_RETRIES")
    crm_sync_retry_base_ms: int = Field(default=400, alias="CRM_SYNC_RETRY_BASE_MS")
    rag_kb_path: str = Field(default="./rag/knowledge_base.json", alias="RAG_KB_PATH")
    rag_top_k: int = Field(default=3, alias="RAG_TOP_K")
    rag_min_score: float = Field(default=1.0, alias="RAG_MIN_SCORE")
    user_policies_path: str = Field(default="./user_policies.json", alias="USER_POLICIES_PATH")
    user_daily_token_limit: int = Field(default=0, alias="USER_DAILY_TOKEN_LIMIT")
    user_token_limit_reserved_response_tokens: int = Field(
        default=280,
        alias="USER_TOKEN_LIMIT_RESERVED_RESPONSE_TOKENS",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-nano", alias="OPENAI_MODEL")
    openai_fallback_model: str = Field(default="gpt-5-mini", alias="OPENAI_FALLBACK_MODEL")
    openai_timeout_ms: int = Field(default=12000, alias="OPENAI_TIMEOUT_MS")
    database_url: str = Field(default="", alias="DATABASE_URL")
    postgres_host: str = Field(default="", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="", alias="POSTGRES_DB")
    postgres_user: str = Field(default="", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    storage_sqlite_path: str = Field(default="./assistant.db", alias="STORAGE_SQLITE_PATH")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def openai_timeout_seconds(self) -> float:
        return max(self.openai_timeout_ms / 1000, 1.0)

    @property
    def crm_sync_timeout_seconds(self) -> float:
        return max(self.crm_sync_timeout_ms / 1000, 1.0)

    @property
    def postgres_database_url(self) -> str:
        host = self.postgres_host.strip()
        db = self.postgres_db.strip()
        user = self.postgres_user.strip()
        if not host or not db or not user:
            return ""

        password = self.postgres_password
        encoded_user = quote_plus(user)
        auth = encoded_user
        if password != "":
            auth = f"{encoded_user}:{quote_plus(password)}"

        return f"postgresql+psycopg://{auth}@{host}:{int(self.postgres_port)}/{db}"

    @property
    def database_url_resolved(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()

        postgres_database_url = self.postgres_database_url
        if postgres_database_url:
            return postgres_database_url

        sqlite_path = Path(self.storage_sqlite_path).expanduser()
        if sqlite_path.is_absolute():
            return f"sqlite:///{sqlite_path}"
        return f"sqlite:///{self.storage_sqlite_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
