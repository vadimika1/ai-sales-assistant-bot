# Production Runbook

Runbook для деплоя `ai-sales-assistant-bot` на VPS с Docker Compose.

## 1. Подготовка сервера

Минимально:
- Ubuntu 22.04+ (или совместимый Linux)
- Docker + Docker Compose plugin
- Открыты порты `80/443` (для reverse proxy) и `8080` (API, если нужен снаружи)
- Домен для webhook, например `bot.example.com`

Проверка:

```bash
docker --version
docker compose version
```

## 2. Подготовка проекта

```bash
mkdir -p /opt/ai-sales-assistant-bot
cd /opt/ai-sales-assistant-bot
# скопируйте сюда проект (git clone / rsync / архив)
cp .env.example .env
```

## 3. Обязательные настройки `.env`

Минимальный production-набор:
- `TELEGRAM_BOT_TOKEN`
- `API_SERVICE_TOKEN` (длинный случайный токен)
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `BOT_RUN_MODE=webhook`
- `BOT_WEBHOOK_URL=https://bot.example.com/telegram/webhook`
- `BOT_WEBHOOK_PATH=/telegram/webhook`
- `BOT_WEBHOOK_PORT=8081`
- `OPENAI_API_KEY` (если нужен реальный AI, а не mock)

Важно:
- `BOT_WEBHOOK_URL` должен совпадать с публичным HTTPS URL, доступным из Telegram.
- Для Docker Compose хост БД внутри сети уже задан как `db`.

## 4. Preflight и миграции

```bash
cd /opt/ai-sales-assistant-bot
python3 scripts/preflight.py --target all
python3 scripts/db_doctor.py --upgrade-head
```

## 5. Первый запуск

```bash
cd /opt/ai-sales-assistant-bot
docker compose up -d --build
docker compose ps
```

Проверка:

```bash
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/health/ready
```

## 6. Nginx для Telegram webhook (HTTPS)

Пример конфига: `deploy/nginx/leadpilot_bot.conf.example`.

Типовой сценарий:
1. Установить nginx и certbot.
2. Скопировать конфиг в `/etc/nginx/sites-available/leadpilot-bot.conf`.
3. Сделать symlink в `/etc/nginx/sites-enabled/`.
4. Выпустить сертификат Let`s Encrypt.
5. `nginx -t && systemctl reload nginx`.

## 7. Обновление без ручных миграций

```bash
cd /opt/ai-sales-assistant-bot
# получить новую версию кода
docker compose up -d --build
docker compose ps
```

`api` на старте сам выполняет `alembic upgrade head`.

## 8. Rollback

1. Вернуться на предыдущую версию кода (предыдущий commit/tag/архив).
2. Пересобрать и поднять сервисы:

```bash
cd /opt/ai-sales-assistant-bot
docker compose up -d --build
```

3. Проверить:

```bash
curl -sS http://127.0.0.1:8080/health/ready
```

## 9. Операционные команды

Логи:

```bash
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f db
```

Перезапуск:

```bash
docker compose restart api bot
```

Состояние сервисов:

```bash
docker compose ps
```

## 10. Быстрая диагностика

- `TelegramUnauthorizedError`: неверный `TELEGRAM_BOT_TOKEN`.
- `password authentication failed`: неверные `POSTGRES_USER/POSTGRES_PASSWORD`.
- `503 /health/ready`: API не может подключиться к БД.
- Webhook не приходит: проверь `BOT_WEBHOOK_URL`, HTTPS сертификат, и проксирование пути `/telegram/webhook`.

## 11. Бэкапы PostgreSQL

Скрипты:
- `scripts/ops/postgres_backup.sh`
- `scripts/ops/postgres_restore.sh`

Быстрый backup:

```bash
cd /opt/ai-sales-assistant-bot
bash scripts/ops/postgres_backup.sh
```

Будут созданы:
- архив `*.sql.gz`
- checksum `*.sha256`

Используемые переменные (`.env`):
- `BACKUP_DIR`
- `BACKUP_RETENTION_DAYS`
- `BACKUP_FILENAME_PREFIX`
- `BACKUP_DB_SERVICE` (по умолчанию `db`)

Restore (восстановление в текущую БД, потенциально разрушительная операция):

```bash
cd /opt/ai-sales-assistant-bot
bash scripts/ops/postgres_restore.sh /path/to/backup.sql.gz --yes
```

## 12. Мониторинг и алерты

Скрипт:
- `scripts/ops/monitor_stack.py`

Что проверяет:
- `MONITOR_READY_URL` (`/health/ready`)
- статус сервисов (`api,bot,db`)
- `docker stats` (CPU/RAM) с порогами
- server-error события в логах API за последние `MONITOR_LOG_LOOKBACK_MINUTES`

Основные переменные (`.env`):
- `MONITOR_READY_URL`
- `MONITOR_REQUIRED_SERVICES`
- `MONITOR_CPU_PERCENT_THRESHOLD`
- `MONITOR_MEM_PERCENT_THRESHOLD`
- `MONITOR_LOG_LOOKBACK_MINUTES`
- `MONITOR_ERROR_LOG_THRESHOLD`
- `MONITOR_ALERT_COOLDOWN_SECONDS`
- `MONITOR_ALERT_TELEGRAM_BOT_TOKEN`
- `MONITOR_ALERT_TELEGRAM_CHAT_ID`

Запуск вручную:

```bash
cd /opt/ai-sales-assistant-bot
python3 scripts/ops/monitor_stack.py
```

Пример cron:
- `deploy/cron/ai_sales_ops.cron.example`

## 13. Админ-управление лимитами и баном

Файл политик:
- `USER_POLICIES_PATH` (по умолчанию `./user_policies.json`)
- пример: `user_policies.example.json`

CLI:
- `scripts/ops/user_control.py`

Примеры:

```bash
cd /opt/ai-sales-assistant-bot
python3 scripts/ops/user_control.py list
python3 scripts/ops/user_control.py ban 777
python3 scripts/ops/user_control.py unban 777
python3 scripts/ops/user_control.py set-limit 777 1500
python3 scripts/ops/user_control.py clear-limit 777
```

Поведение API `/suggest`:
- `403`, если пользователь в `banned_user_ids`
- персональный лимит из `daily_token_limit_overrides` имеет приоритет над `USER_DAILY_TOKEN_LIMIT`
