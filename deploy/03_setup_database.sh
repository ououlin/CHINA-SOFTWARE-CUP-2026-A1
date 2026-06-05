#!/usr/bin/env bash
# ============================================================
# 03 初始化 PostgreSQL 并创建库与角色
# 需 root： sudo DB_PASSWORD='你的强密码' bash deploy/03_setup_database.sh
# 幂等：可重复执行（已存在的角色/库会跳过）。
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "请用 root 运行： sudo bash $0" >&2; exit 1; fi

DB_NAME="${DB_NAME:-devrepair}"
DB_USER="${DB_USER:-devrepair}"
DB_PASSWORD="${DB_PASSWORD:-}"
if [[ -z "$DB_PASSWORD" ]]; then
  echo "[警告] 未提供 DB_PASSWORD，使用默认 'devrepair_pwd'（演示可，生产务必改强密码）"
  DB_PASSWORD="devrepair_pwd"
fi

# 数据目录与服务名（RHEL/麒麟默认）
PGDATA="${PGDATA:-/var/lib/pgsql/data}"
SVC="${SVC:-postgresql}"

# 1) 初始化数据目录（首次）
if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
  echo "==> 初始化数据库数据目录 $PGDATA"
  if command -v postgresql-setup >/dev/null 2>&1; then
    postgresql-setup --initdb || postgresql-setup initdb
  else
    # 退路：直接用 initdb（postgres 用户）
    INITDB=$(command -v initdb || ls /usr/pgsql-*/bin/initdb 2>/dev/null | head -n1)
    sudo -u postgres "$INITDB" -D "$PGDATA"
  fi
else
  echo "==> 数据目录已初始化，跳过 initdb"
fi

# 2) 启动并设开机自启
echo "==> 启动并启用 $SVC"
systemctl enable --now "$SVC"

# 3) 创建角色与库（幂等）
echo "==> 创建角色 $DB_USER 与库 $DB_NAME（如已存在则跳过）"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;
SQL

# 建库（若不存在）。CREATE DATABASE 不能放进 DO 块，单独判断。
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER} ENCODING 'UTF8';"
else
  echo "    库 ${DB_NAME} 已存在，跳过"
fi

# 4) 可选：若已编译 pgvector，则启用扩展（失败不致命）
sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null \
  && echo "    已启用 pgvector 扩展" \
  || echo "    [提示] 未启用 pgvector（未编译亦可，应用用 JSON+内存余弦）"

# 5) 放开本地密码登录（pg_hba：localhost 用 md5/scram）
HBA="$PGDATA/pg_hba.conf"
if [[ -f "$HBA" ]] && ! grep -qE "^host\s+${DB_NAME}\s+${DB_USER}\s+127.0.0.1/32" "$HBA"; then
  echo "==> 追加 pg_hba 本地登录规则"
  echo "host    ${DB_NAME}    ${DB_USER}    127.0.0.1/32    scram-sha-256" >> "$HBA"
  echo "host    ${DB_NAME}    ${DB_USER}    ::1/128         scram-sha-256" >> "$HBA"
  systemctl reload "$SVC"
fi

echo
echo "✅ 数据库就绪。请把下面这行填入 backend/.env（替换 .env.production.example 中的占位）："
echo "   DATABASE_URL=postgresql+pg8000://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}"
