#!/usr/bin/env bash
# PostgreSQL backup and isolated restore verification. Never restores over source DB.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
ENV_FILE="${ENV_FILE:-$ROOT/backend/.env}"
OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-$ROOT/evidence/backups}"
ACTION="${1:-backup}"

read_url() {
  local explicit="$1"
  if [[ -n "$explicit" ]]; then
    printf '%s' "$explicit"
  elif [[ -f "$ENV_FILE" ]]; then
    grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '"'
  fi
}

SOURCE_URL="$(read_url "${DATABASE_URL:-}")"
SOURCE_URL="${SOURCE_URL/postgresql+pg8000:/postgresql:}"
[[ "$SOURCE_URL" == postgresql://* ]] || {
  echo "DATABASE_URL must be a PostgreSQL URL" >&2
  exit 2
}

mkdir -p "$OUTPUT_DIR"

case "$ACTION" in
  backup)
    command -v pg_dump >/dev/null || { echo "pg_dump is required" >&2; exit 3; }
    command -v pg_restore >/dev/null || { echo "pg_restore is required" >&2; exit 3; }
    command -v sha256sum >/dev/null || { echo "sha256sum is required" >&2; exit 3; }
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup="$OUTPUT_DIR/device-repair-$stamp.dump"
    pg_dump --dbname="$SOURCE_URL" --format=custom --no-owner --file="$backup"
    sha256sum "$backup" > "$backup.sha256"
    pg_restore --list "$backup" > "$backup.contents"
    echo "backup=$backup"
    echo "checksum=$backup.sha256"
    ;;
  verify)
    backup="${2:-}"
    restore_url="${RESTORE_DATABASE_URL:-}"
    restore_url="${restore_url/postgresql+pg8000:/postgresql:}"
    [[ -f "$backup" ]] || { echo "usage: $0 verify <backup.dump>" >&2; exit 2; }
    [[ "$restore_url" == postgresql://* ]] || {
      echo "RESTORE_DATABASE_URL must name a dedicated disposable PostgreSQL database" >&2
      exit 2
    }
    [[ "$restore_url" != "$SOURCE_URL" ]] || {
      echo "refusing to restore over source DATABASE_URL" >&2
      exit 2
    }
    command -v pg_restore >/dev/null || { echo "pg_restore is required" >&2; exit 3; }
    command -v psql >/dev/null || { echo "psql is required" >&2; exit 3; }
    if [[ -f "$backup.sha256" ]]; then
      (cd "$(dirname "$backup")" && sha256sum --check "$(basename "$backup").sha256")
    fi
    pg_restore --dbname="$restore_url" --clean --if-exists --no-owner "$backup"
    psql "$restore_url" -v ON_ERROR_STOP=1 -c \
      "SELECT 'documents' AS table_name, count(*) AS rows FROM documents UNION ALL SELECT 'doc_chunks', count(*) FROM doc_chunks UNION ALL SELECT 'users', count(*) FROM users;" \
      | tee "$backup.restore-check.txt"
    echo "restore verification passed: $backup.restore-check.txt"
    ;;
  *)
    echo "usage: $0 {backup|verify <backup.dump>}" >&2
    exit 2
    ;;
esac
