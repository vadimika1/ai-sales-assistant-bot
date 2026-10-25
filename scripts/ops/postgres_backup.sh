#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups/postgres}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
BACKUP_FILENAME_PREFIX="${BACKUP_FILENAME_PREFIX:-ai_sales_assistant}"
BACKUP_DB_SERVICE="${BACKUP_DB_SERVICE:-db}"

POSTGRES_DB="${POSTGRES_DB:-ai_sales_assistant}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[backup] docker не найден." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILENAME_PREFIX}_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "[backup] creating ${BACKUP_FILE}"

docker compose exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  "${BACKUP_DB_SERVICE}" \
  sh -lc "pg_dump --clean --if-exists --no-owner --no-privileges -U \"${POSTGRES_USER}\" -d \"${POSTGRES_DB}\"" \
  | gzip -9 > "${BACKUP_FILE}"

gzip -t "${BACKUP_FILE}"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
else
  shasum -a 256 "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
fi

if [[ "${BACKUP_RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  find "${BACKUP_DIR}" -type f -name "${BACKUP_FILENAME_PREFIX}_${POSTGRES_DB}_*.sql.gz" \
    -mtime +"${BACKUP_RETENTION_DAYS}" -print -delete || true
  find "${BACKUP_DIR}" -type f -name "${BACKUP_FILENAME_PREFIX}_${POSTGRES_DB}_*.sql.gz.sha256" \
    -mtime +"${BACKUP_RETENTION_DAYS}" -print -delete || true
fi

echo "[backup] done"
echo "[backup] file: ${BACKUP_FILE}"
echo "[backup] checksum: ${CHECKSUM_FILE}"
