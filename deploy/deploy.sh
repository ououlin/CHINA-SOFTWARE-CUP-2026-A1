#!/usr/bin/env bash
# =============================================================
# deploy.sh — 银河麒麟 V10/V11 + LoongArch 一键部署
#
# 用法：sudo bash deploy/deploy.sh
#
# 前置（两步手动操作，脚本会检测并提示）：
#   1. 填好 backend/.env（密钥），或先跑脚本让它生成模板再补填
#   2. 把开发机构建好的 frontend/dist 上传到服务器同路径
#
# PostgreSQL 生产模式会在扩展缺失时调用 02_install_pgvector.sh
# 诊断：bash deploy/00_smoke_test.sh             （依赖冒烟测试）
# =============================================================
set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}==>${NC} $*"; }
warn()  { echo -e "${YELLOW}[警告]${NC} $*"; }
error() { echo -e "${RED}[错误]${NC} $*" >&2; }

[[ $EUID -ne 0 ]] && { error "请用 root 运行： sudo bash $0"; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
BACKEND="$ROOT/backend"
ENV_FILE="$BACKEND/.env"
RUN_USER="${RUN_USER:-devrepair}"

info "仓库根：$ROOT"
[[ -d "$BACKEND" ]] || { error "未找到 $BACKEND，请确认仓库已 clone 到 /opt/device-repair"; exit 1; }

# ══════════════════════════════════════════════════════════════
# 1. 系统依赖
# ══════════════════════════════════════════════════════════════
info "安装系统依赖"
PM=dnf; command -v dnf >/dev/null 2>&1 || PM=yum
info "使用包管理器：$PM"

$PM install -y python3 python3-pip git nginx python3-devel gcc gcc-c++ make tar
$PM install -y postgresql-server postgresql-contrib || warn "PostgreSQL 包名可能不同，如用 SQLite 可忽略"
$PM install -y postgresql-devel || true   # 仅编译 pgvector 时需要

# ══════════════════════════════════════════════════════════════
# 2. .env 检查
# ══════════════════════════════════════════════════════════════
if [[ ! -f "$ENV_FILE" ]]; then
  info "生成 .env 模板，请补填密钥后重跑本脚本"
  cp "$HERE/.env.production.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo
  echo "  请编辑 $ENV_FILE，至少填写："
  echo "    DEEPSEEK_API_KEY=<your_key>"
  echo "    DASHSCOPE_API_KEY=<your_key>"
  echo "    DATABASE_URL=postgresql+pg8000://devrepair:<密码>@127.0.0.1:5432/devrepair"
  echo "    JWT_SECRET=<随机字符串>"
  echo
  exit 2
fi

# 读取数据库与检索配置
DB_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')"
VECTOR_BACKEND="$(sed -n 's/^VECTOR_BACKEND=//p' "$ENV_FILE" | tail -n1 | tr -d '"')"
VECTOR_BACKEND="${VECTOR_BACKEND:-auto}"
EMBEDDING_DIM="$(sed -n 's/^EMBEDDING_DIM=//p' "$ENV_FILE" | tail -n1 | sed 's/[[:space:]#].*$//' | tr -d '"')"
EMBEDDING_DIM="${EMBEDDING_DIM:-512}"
[[ "$EMBEDDING_DIM" =~ ^[1-9][0-9]*$ ]] || { error "EMBEDDING_DIM 必须为正整数"; exit 1; }

# ══════════════════════════════════════════════════════════════
# 3. 数据库初始化（仅 PostgreSQL；SQLite 跳过）
# ══════════════════════════════════════════════════════════════
if [[ "$DB_URL" == postgresql* ]]; then
  info "检测到 PostgreSQL，初始化数据库"

  # 解析连接串：postgresql+pg8000://user:pass@host:port/dbname
  DB_USER="$(echo "$DB_URL" | sed -E 's|.*://([^:]+):.*|\1|')"
  DB_PASS="$(echo "$DB_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')"
  DB_NAME="$(echo "$DB_URL" | sed -E 's|.*/([^?]+).*|\1|')"
  [[ "$DB_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    error "DATABASE_URL 用户名仅允许字母、数字和下划线，且不能以数字开头"; exit 1;
  }
  [[ "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    error "DATABASE_URL 数据库名仅允许字母、数字和下划线，且不能以数字开头"; exit 1;
  }
  PGDATA="${PGDATA:-/var/lib/pgsql/data}"
  SVC=postgresql

  # 初始化数据目录
  if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    info "初始化 PostgreSQL 数据目录"
    if command -v postgresql-setup >/dev/null 2>&1; then
      postgresql-setup --initdb || postgresql-setup initdb
    else
      INITDB=$(command -v initdb 2>/dev/null || ls /usr/pgsql-*/bin/initdb 2>/dev/null | head -n1)
      sudo -u postgres "$INITDB" -D "$PGDATA"
    fi
  fi

  systemctl enable --now "$SVC"

  # 安全处理：对DB密码中的特殊字符进行转义（单引号替换为两个单引号）
  # 防止密码包含 ' " \ $ 等特殊字符导致SQL语法错误或命令注入
  DB_PASS_ESCAPED="${DB_PASS//\'/\'\'}"
  DB_USER_ESCAPED="${DB_USER//\'/\'\'}"
  DB_NAME_ESCAPED="${DB_NAME//\'/\'\'}"

  # 创建用户与库（幂等）
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER_ESCAPED}') THEN
    CREATE ROLE ${DB_USER_ESCAPED} LOGIN PASSWORD '${DB_PASS_ESCAPED}';
  ELSE
    ALTER ROLE ${DB_USER_ESCAPED} WITH PASSWORD '${DB_PASS_ESCAPED}';
  END IF;
END
\$\$;
SQL
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME_ESCAPED}'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME_ESCAPED} OWNER ${DB_USER_ESCAPED} ENCODING 'UTF8';"
  fi

  # pg_hba：放开本地密码登录
  HBA="$PGDATA/pg_hba.conf"
  if [[ -f "$HBA" ]] && ! grep -qE "^host\s+${DB_NAME_ESCAPED}\s+${DB_USER_ESCAPED}\s+127.0.0.1/32" "$HBA"; then
    echo "host  ${DB_NAME_ESCAPED}  ${DB_USER_ESCAPED}  127.0.0.1/32  scram-sha-256" >> "$HBA"
    echo "host  ${DB_NAME_ESCAPED}  ${DB_USER_ESCAPED}  ::1/128       scram-sha-256" >> "$HBA"
    systemctl reload "$SVC"
  fi

  if [[ "$VECTOR_BACKEND" == "auto" || "$VECTOR_BACKEND" == "pgvector" ]]; then
    if ! sudo -u postgres psql -tAc \
      "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
      info "系统尚未安装 pgvector，开始源码编译"
      bash "$HERE/02_install_pgvector.sh"
    fi
    sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME_ESCAPED}" <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
    info "vector 与 pg_trgm 扩展已启用"
  fi
else
  info "使用 SQLite（$DB_URL），跳过 PostgreSQL 初始化"
fi

# ══════════════════════════════════════════════════════════════
# 4. 后端：运行用户 + venv + 依赖 + 种子 + systemd
# ══════════════════════════════════════════════════════════════
info "创建运行用户 $RUN_USER（若已存在则跳过）"
id "$RUN_USER" >/dev/null 2>&1 || useradd -r -s /sbin/nologin -d "$ROOT" "$RUN_USER"
chown -R "$RUN_USER":"$RUN_USER" "$ROOT"

info "创建 venv 并安装后端依赖"
runuser -u "$RUN_USER" -- bash -lc "
  set -e
  cd '$BACKEND'
  [[ -d .venv ]] || python3 -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip -q
  ./.venv/bin/python -m pip install -r requirements-server.txt -q
"

info "初始化数据库表与种子数据"
if ! runuser -u "$RUN_USER" -- bash -lc "cd '$BACKEND' && ./.venv/bin/python -m app.seed"; then
  error "种子初始化失败，请检查 .env 中 DATABASE_URL 与 API Key 配置后重跑"
  exit 1
fi

if [[ "$DB_URL" == postgresql* ]]; then
  if [[ "$VECTOR_BACKEND" == "auto" || "$VECTOR_BACKEND" == "pgvector" ]]; then
    info "校验向量列并创建 HNSW / trigram 索引（维度 $EMBEDDING_DIM）"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -v embedding_dim="$EMBEDDING_DIM" \
      -d "${DB_NAME_ESCAPED}" -f "$HERE/03_migrate_pgvector.sql"
  fi
fi

info "注册并启动 systemd 服务"
UNIT=/etc/systemd/system/device-repair-backend.service
sed -e "s#/opt/device-repair#$ROOT#g" \
    -e "s#^User=.*#User=$RUN_USER#" \
    -e "s#^Group=.*#Group=$RUN_USER#" \
    "$HERE/systemd/device-repair-backend.service" > "$UNIT"
systemctl daemon-reload
systemctl enable --now device-repair-backend

sleep 2
info "健康检查"
curl -fsS http://127.0.0.1:8000/api/health && echo || {
  warn "健康检查未通过，查看日志：journalctl -u device-repair-backend -n 50"
}

# ══════════════════════════════════════════════════════════════
# 5. 前端 + Nginx
# ══════════════════════════════════════════════════════════════
DIST="$ROOT/frontend/dist"
if [[ ! -f "$DIST/index.html" ]]; then
  warn "未找到 $DIST/index.html"
  echo "  请在开发机（Windows）执行："
  echo "    cd frontend && npm run build"
  echo "  将生成的 frontend/dist.zip 上传到服务器后执行："
  echo "    sudo unzip -o ~/下载/dist.zip -d $ROOT/frontend/"
  echo "  然后重跑本脚本完成前端部署。"
  echo
  echo "  后端已部署完成，API 可用：http://127.0.0.1:8000/api/health"
  exit 0
fi

info "写入 Nginx 站点配置"
CONF=/etc/nginx/conf.d/device-repair.conf
sed "s#/opt/device-repair#$ROOT#g" "$HERE/nginx/device-repair.conf" > "$CONF"

# SELinux
if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
  info "SELinux：放开 nginx 反代联网"
  setsebool -P httpd_can_network_connect 1 || warn "setsebool 失败，若 502 请手动执行"
  command -v restorecon >/dev/null 2>&1 && restorecon -R "$DIST" || true
fi

# 防火墙
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  info "放行 80/tcp"
  firewall-cmd --permanent --add-service=http >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
fi

info "校验并启动 Nginx"
nginx -t
systemctl enable nginx
systemctl is-active --quiet nginx && systemctl reload nginx || systemctl start nginx

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "   浏览器访问：http://${IP:-<服务器IP>}/"
echo "   演示账号：worker/worker123 、auditor/auditor123 、admin/admin123"
echo
echo "   常用运维命令："
echo "     sudo systemctl restart device-repair-backend   # 重启后端"
echo "     journalctl -u device-repair-backend -f         # 查看日志"
echo "     sudo git pull && sudo bash deploy/deploy.sh    # 更新部署"
