from app.config import Settings


def test_database_url_resolved_prefers_database_url() -> None:
    settings = Settings.model_construct(
        database_url="postgresql+psycopg://db",
        postgres_host="127.0.0.1",
        postgres_db="ignored",
        postgres_user="ignored",
        storage_sqlite_path="./x.db",
    )
    assert settings.database_url_resolved == "postgresql+psycopg://db"


def test_database_url_resolved_builds_postgres_url_from_parts() -> None:
    settings = Settings.model_construct(
        database_url="",
        postgres_host="127.0.0.1",
        postgres_port=5433,
        postgres_db="ai_sales",
        postgres_user="postgres",
        postgres_password="pass@word",
        storage_sqlite_path="./assistant.db",
    )
    assert (
        settings.database_url_resolved
        == "postgresql+psycopg://postgres:pass%40word@127.0.0.1:5433/ai_sales"
    )


def test_database_url_resolved_falls_back_to_sqlite_path() -> None:
    settings = Settings.model_construct(
        database_url="",
        postgres_host="",
        postgres_db="",
        postgres_user="",
        storage_sqlite_path="./assistant.db",
    )
    assert settings.database_url_resolved == "sqlite:///./assistant.db"


def test_rag_settings_are_accessible() -> None:
    settings = Settings.model_construct(rag_kb_path="./rag/knowledge_base.json", rag_top_k=4, rag_min_score=0.7)
    assert settings.rag_kb_path == "./rag/knowledge_base.json"
    assert settings.rag_top_k == 4
    assert settings.rag_min_score == 0.7


def test_user_token_limit_settings_are_accessible() -> None:
    settings = Settings.model_construct(
        user_policies_path="./user_policies.json",
        user_daily_token_limit=4000,
        user_token_limit_reserved_response_tokens=220,
    )
    assert settings.user_policies_path == "./user_policies.json"
    assert settings.user_daily_token_limit == 4000
    assert settings.user_token_limit_reserved_response_tokens == 220


def test_bot_webhook_settings_are_accessible() -> None:
    settings = Settings.model_construct(
        bot_run_mode="webhook",
        bot_webhook_url="https://example.com/tg/webhook",
        bot_webhook_path="/tg/webhook",
        bot_webhook_host="0.0.0.0",
        bot_webhook_port=8081,
    )
    assert settings.bot_run_mode == "webhook"
    assert settings.bot_webhook_url == "https://example.com/tg/webhook"
    assert settings.bot_webhook_path == "/tg/webhook"
    assert settings.bot_webhook_port == 8081
