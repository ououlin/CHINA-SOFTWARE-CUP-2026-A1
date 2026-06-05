#!/usr/bin/env bash
# ============================================================
# 04 部署后端：创建运行用户 + venv + 装依赖 + 初始化数据 + 注册 systemd 服务
# 需 root： sudo bash deploy/04_deploy_backend.sh
# 前置：已跑 01（系统依赖）、03（数据库），并已填好 backend/.env 的密钥。
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "请用 root 运行： sudo bash $0" >&2; exit 1; fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"               # 仓库根（建议为 /opt/device-repair）
BACKEND="$ROOT/backend"
RUN_USER="${RUN_USER:-devrepair}"

echo "==> 仓库根：$ROOT"
[[ -d "$BACKEND" ]] || { echo "未找到 $BACKEND，请把仓库放到 /opt/device-repair 后再运行" >&2; exit 1; }

# 1) 运行用户
if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "==> 创建系统用户 $RUN_USER"
  useradd -r -s /sbin/nologin -d "$ROOT" "$RUN_USER"
fi
chown -R "$RUN_USER":"$RUN_USER" "$ROOT"

# 2) .env 检查（密钥必须先填）
if [[ ! -f "$BACKEND/.env" ]]; then
  echo "==> 未发现 backend/.env，已从模板复制，请填入密钥后重跑本脚本："
  cp "$HERE/.env.production.example" "$BACKEND/.env"
  chown "$RUN_USER":"$RUN_USER" "$BACKEND/.env"; chmod 600 "$BACKEND/.env"
  echo "    编辑： vi $BACKEND/.env   （至少填 DEEPSEEK_API_KEY、DASHSCOPE_API_KEY、DATABASE_URL、JWT_SECRET）"
  exit 2
fi
if grep -qE "^(DEEPSEEK_API_KEY|DASHSCOPE_API_KEY)=$" "$BACKEND/.env"; then
  echo "[警告] backend/.env 中存在空的 API Key，问答/嵌入将不可用。请补全后重跑。" >&2
  exit 2
fi

# 3) venv + 依赖（以运行用户身份）
echo "==> 创建虚拟环境并安装依赖（requirements-server.txt）"
runuser -u "$RUN_USER" -- bash -lc "
  set -e
  cd '$BACKEND'
  [[ -d .venv ]] || python3 -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip
  ./.venv/bin/python -m pip install -r requirements-server.txt
"

# 4) 初始化数据库表 + 种子（账号/手册/SOP/案例/图谱）
echo "==> 初始化数据与种子（python -m app.seed）"
if ! runuser -u "$RUN_USER" -- bash -lc "cd '$BACKEND' && ./.venv/bin/python -m app.seed"; then
  echo "[错误] 种子初始化失败：多为 .env 密钥或 DATABASE_URL 配置问题，请核对后重跑。" >&2
  exit 1
fi

# 5) systemd 服务
echo "==> 安装 systemd 服务"
UNIT=/etc/systemd/system/device-repair-backend.service
sed -e "s#/opt/device-repair#$ROOT#g" -e "s#^User=.*#User=$RUN_USER#" -e "s#^Group=.*#Group=$RUN_USER#" \
    "$HERE/systemd/device-repair-backend.service" > "$UNIT"
systemctl daemon-reload
systemctl enable --now device-repair-backend

sleep 2
echo
echo "==> 服务状态："
systemctl --no-pager --full status device-repair-backend | head -n 12 || true
echo
echo "==> 健康检查："
curl -fsS http://127.0.0.1:8000/api/health && echo || echo "[警告] 健康检查未通过，看日志： journalctl -u device-repair-backend -n 50"
echo
echo "完成。下一步：bash deploy/05_deploy_frontend.sh 部署前端与 Nginx。"
