# AI Sales Assistant Bot (Standalone)

Telegram-бот с ИИ для менеджеров продаж: предлагает ответ клиенту и следующий шаг по сделке, опирается на базу знаний (RAG), не выдумывает цены и сроки. Лимиты токенов на пользователя, синхронизация с CRM, набор эвалов.

An AI Telegram assistant for sales managers: it drafts a reply to the client and the next step in the deal, grounded in a knowledge base (RAG) and barred from inventing prices or deadlines. Per-user token limits, CRM sync and an eval suite.

Автор: [Вадим Антонович](https://vadim.tabletools.ru).

## Стек

- Python 3.10+
- aiogram 3
- FastAPI
- OpenAI API (`gpt-5-nano` + fallback `gpt-5-mini`)
- PostgreSQL + Alembic (этап 2)
- SQLite fallback для локального запуска без PostgreSQL

## Быстрый старт

1. Подготовить окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
```

2. Заполнить `.env`:

- `TELEGRAM_BOT_TOKEN`
- `BOT_RUN_MODE` (`polling` или `webhook`)
- `OPENAI_API_KEY` (опционально: если пусто, включается локальный mock-режим без внешнего AI API)
- `DATABASE_URL` или набор `POSTGRES_*` (`HOST/PORT/DB/USER/PASSWORD`) для PostgreSQL
- `API_SERVICE_TOKEN` (рекомендуется; одинаковый для API и бота)
- `CRM_SYNC_URL` (опционально: webhook/endpoint CRM для этапа sync)
- `RAG_KB_PATH` (путь к локальной базе знаний JSON)
- `USER_POLICIES_PATH` (JSON с баном пользователей и персональными лимитами)
- `USER_DAILY_TOKEN_LIMIT` (дневной лимит токенов на одного пользователя; `0` отключает лимит)

Проверьте runtime-конфигурацию:

```bash
python3 scripts/preflight.py --target all
```

Если используете PostgreSQL, перед запуском API примените миграции:

```bash
python3 scripts/db_doctor.py --upgrade-head
```

3. Запустить API:

```bash
api
```

4. В отдельной вкладке запустить бота:

```bash
bot
```

## PostgreSQL и миграции (этап 2)

`DATABASE_URL` имеет приоритет. Если он пустой, проект автоматически собирает DSN из:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Проверка подключения:

```bash
python3 scripts/db_doctor.py
```

Проверка + применение миграций:

```bash
python3 scripts/db_doctor.py --upgrade-head
```

Если видите `password authentication failed`, значит не совпадают логин/пароль в `.env` и у вашего PostgreSQL.

Проверка валидности конфигурации без запуска процессов:

```bash
python3 scripts/preflight.py --target api
python3 scripts/preflight.py --target bot
```

## Прод-контур (Docker Compose)

1. Подготовьте `.env` (минимум: `TELEGRAM_BOT_TOKEN`, `API_SERVICE_TOKEN`):

```bash
cp .env.example .env
```

2. Запустите стек:

```bash
docker compose up -d --build
```

Поднимаются сервисы:
- `db` (PostgreSQL)
- `api` (FastAPI + автоматический `alembic upgrade head` при старте)
- `bot` (aiogram)

В compose `api` и `bot` подключаются к БД через `POSTGRES_*` (с `POSTGRES_HOST=db`), либо через явный `DATABASE_URL`, если он задан.

3. Проверка API:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/health/ready
```

## CI

Добавлен GitHub Actions workflow:

- `.github/workflows/ci.yml`

Пайплайн проверяет:
- `preflight` (api + bot)
- `db_doctor --upgrade-head`
- `ruff`
- `pytest`
- `docker compose config`

## Deploy Runbook

Пошаговый деплой и эксплуатация на VPS:

- `docs/PRODUCTION_RUNBOOK.md`
- пример nginx-конфига: `deploy/nginx/leadpilot_bot.conf.example`
- пример cron для backup/monitoring: `deploy/cron/ai_sales_ops.cron.example`

### Режимы Telegram бота

- `polling` (по умолчанию):
  - `BOT_RUN_MODE=polling`
  - `BOT_WEBHOOK_URL` не нужен

- `webhook`:
  - `BOT_RUN_MODE=webhook`
  - задайте `BOT_WEBHOOK_URL`, например `https://example.com/telegram/webhook`
  - внутри контейнера бот слушает `BOT_WEBHOOK_HOST:BOT_WEBHOOK_PORT` и `BOT_WEBHOOK_PATH`
  - если используете reverse proxy, прокиньте путь `BOT_WEBHOOK_PATH` на контейнер `bot`

## Endpoint

- `GET /health`
- `GET /health/ready` (readiness: проверяет подключение к БД, `503` если БД недоступна)
- `POST /api/v1/ai/suggest`
- `POST /api/v1/ai/feedback`
- `GET /api/v1/ai/metrics?days=7`

API возвращает `X-Request-ID` в каждом ответе. Можно передать свой `X-Request-ID` в запросе для сквозной трассировки в логах.
Ошибки API возвращаются в едином формате:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Ошибка валидации запроса.",
    "request_id": "..."
  }
}
```

Пример запроса:

```json
{
  "manager_message": "Клиент спрашивает цену и сроки",
  "conversation": [
    { "role": "client", "text": "Сколько стоит и когда старт?" }
  ],
  "lead_context": { "source": "telegram" }
}
```

## Тесты

```bash
pytest -q
```

## Mini Eval

Регрессионный прогон качества подсказок:

```bash
python3 scripts/run_eval.py --base-url http://127.0.0.1:8080
```

Если включен `API_SERVICE_TOKEN`, добавьте его:

```bash
python3 scripts/run_eval.py --service-token "$API_SERVICE_TOKEN"
```

`evals/cases.json` поддерживает проверки:
- `expected_intent`
- `expected_next_action`
- `expected_lead_stage`
- `required_reply_substrings`
- `forbidden_reply_substrings`

## Telegram flow

- При первом `/start` бот попросит выбрать язык интерфейса: `Русский` или `English`.
- `/ai <текст>`: запрос подсказки.
- `/language`: сменить язык интерфейса.
- Кнопки под подсказкой:
  - `✅ Принять` -> feedback `accepted`
  - `✏️ Изменить` -> бот попросит прислать исправленный текст, затем сохранит `edited`
  - `❌ Отклонить` -> feedback `rejected`

`pending edit` хранится в БД, поэтому состояние редактирования не теряется после перезапуска бота.

## Безопасность и устойчивость

- API поддерживает проверку заголовка `X-Service-Token` (включается, если задан `API_SERVICE_TOKEN`).
- Встроен rate limit:
  - `API_RATE_LIMIT_SUGGEST_PER_MINUTE`
  - `API_RATE_LIMIT_FEEDBACK_PER_MINUTE`
- В `meta` ответа `/suggest` возвращаются `prompt_tokens`, `completion_tokens`, `total_tokens`.
- В `/metrics` агрегируются токены: `prompt_tokens_total`, `completion_tokens_total`, `total_tokens_total`.
- Клиент бота делает автоматические ретраи на временных ошибках (`429/5xx`) с backoff:
  - `BOT_API_MAX_RETRIES`
  - `BOT_API_RETRY_BASE_MS`
- CRM sync (если задан `CRM_SYNC_URL`) отправляет `summary/lead_stage/next_action` с retry:
  - `CRM_SYNC_TIMEOUT_MS`
  - `CRM_SYNC_MAX_RETRIES`
  - `CRM_SYNC_RETRY_BASE_MS`
  - `CRM_SYNC_TOKEN` (опциональный Bearer token)
- Исходы CRM sync сохраняются в `crm_sync_log` (`success/failed`, попытки, HTTP статус, ошибка).
- Можно ограничить расход для тестового бота:
  - `USER_DAILY_TOKEN_LIMIT` (лимит на пользователя/24ч)
  - `USER_TOKEN_LIMIT_RESERVED_RESPONSE_TOKENS` (резерв на ответ при предчеке лимита)
  - `USER_POLICIES_PATH` (бан-лист и персональные лимиты)
  - Для быстрой проверки лимита по пользователю добавлен составной индекс `request_user_id + created_at`.
- Добавлены операционные скрипты:
  - backup: `scripts/ops/postgres_backup.sh`
  - restore: `scripts/ops/postgres_restore.sh`
  - monitoring + alerts: `scripts/ops/monitor_stack.py`
  - user ban/limits control: `scripts/ops/user_control.py`

## Легкий RAG

- Перед генерацией подсказки сервис выбирает релевантные материалы из локальной базы знаний (`RAG_TOP_K`).
- Поиск работает по лексическому overlap (`manager_message` + `conversation`) без внешних векторных сервисов.
- По умолчанию используется файл `rag/knowledge_base.json`.

Минимальный формат записи:

```json
{
  "id": "pricing_policy",
  "title": "Правила обсуждения бюджета",
  "text": "Сначала уточните цель, срок и бюджет.",
  "tags": ["цена", "бюджет"]
}
```

## Guardrails AI

- Если ответ модели содержит рискованные обещания (`гарантия`, `100%`, `точно`) или неподтвержденные числовые офферы, ответ автоматически переводится в безопасный режим:
  - `intent=qualification`
  - `next_action=ask_clarifying_question`
  - безопасный текст с запросом уточнений по цели/срокам/бюджету.
