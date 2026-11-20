#!/usr/bin/env bash
# ============================================================
# 02 编译安装 pgvector（PostgreSQL 生产检索必需）
# 需 root： sudo bash deploy/02_install_pgvector.sh
#
# 说明：SQLite 回退可用 JSON + 应用层检索跑通演示；生产 PostgreSQL 路径
#       使用 vector 列和 HNSW，因此必须安装 pgvector 并保留实机编译记录。
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "请用 root 运行： sudo bash $0" >&2; exit 1; fi

PGVECTOR_VERSION="${PGVECTOR_VERSION:-v0.7.4}"
WORK="${WORK:-/usr/local/src}"

# 定位 pg_config（决定向哪个 PostgreSQL 安装扩展）
if command -v pg_config >/dev/null 2>&1; then
  PG_CONFIG=pg_config
elif ls /usr/pgsql-*/bin/pg_config >/dev/null 2>&1; then
  PG_CONFIG=$(ls /usr/pgsql-*/bin/pg_config | head -n1)
else
  echo "未找到 pg_config，请先安装 postgresql-devel（含开发头文件）。" >&2
  exit 1
fi
echo "==> 使用 PG_CONFIG=$PG_CONFIG"
"$PG_CONFIG" --version

command -v make >/dev/null 2>&1 || { echo "缺少 make，请先装 make/gcc" >&2; exit 1; }
command -v gcc  >/dev/null 2>&1 || { echo "缺少 gcc，请先装 gcc" >&2; exit 1; }

mkdir -p "$WORK"; cd "$WORK"
if [[ ! -d pgvector ]]; then
  echo "==> 克隆 pgvector $PGVECTOR_VERSION"
  git clone --branch "$PGVECTOR_VERSION" --depth 1 https://github.com/pgvector/pgvector.git
fi
cd pgvector

echo "==> 编译（PG_CONFIG=$PG_CONFIG）"
make clean || true
make PG_CONFIG="$PG_CONFIG"
echo "==> 安装"
make PG_CONFIG="$PG_CONFIG" install

echo
echo "✅ pgvector 编译安装完成。接下来在目标库启用扩展："
echo "   sudo -u postgres psql -d devrepair -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
echo "   sudo -u postgres psql -d devrepair -v embedding_dim=1024 -f deploy/03_migrate_pgvector.sql"
