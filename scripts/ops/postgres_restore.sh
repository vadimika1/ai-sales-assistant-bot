#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Использование:
  $(basename "$0") <backup.sql.gz|backup.sql> --yes

Пример:
  $(basename "$0") ./backups/postgres/ai_sales_assistant_ai_sales_assistant_20260304T190000Z.sql.gz --yes
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 1
fi

BACKUP_FILE="$1"
CONFIRM_FLAG="$2"

if [[ "${CONFIRM_FLAG}" != "--yes" ]]; then
  echo "[restore] для выполнения укажите флаг --yes." >&2
  exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "[restore] файл не найден: ${BACKUP_FILE}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BACKUP_DB_SERVICE="${BACKUP_DB_SERVICE:-db}"
POSTGRES_DB="${POSTGRES_DB:-ai_sales_assistant}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[restore] docker не найден." >&2
  exit 1
fi

echo "[restore] target db=${POSTGRES_DB}, user=${POSTGRES_USER}, service=${BACKUP_DB_SERVICE}"
echo "[restore] source=${BACKUP_FILE}"

if [[ "${BACKUP_FILE}" == *.gz ]]; then
  gzip -dc "${BACKUP_FILE}" \
    | docker compose exec -T \
      -e PGPASSWORD="${POSTGRES_PASSWORD}" \
      "${BACKUP_DB_SERVICE}" \
      sh -lc "psql -v ON_ERROR_STOP=1 -U \"${POSTGRES_USER}\" -d \"${POSTGRES_DB}\""
else
  cat "${BACKUP_FILE}" \
    | docker compose exec -T \
      -e PGPASSWORD="${POSTGRES_PASSWORD}" \
      "${BACKUP_DB_SERVICE}" \
      sh -lc "psql -v ON_ERROR_STOP=1 -U \"${POSTGRES_USER}\" -d \"${POSTGRES_DB}\""
fi

echo "[restore] done"
