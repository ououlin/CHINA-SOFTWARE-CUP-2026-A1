#!/usr/bin/env bash
# ============================================================
# 00 依赖冒烟测试（M0 排雷）—— 在龙芯虚机上评估各依赖可装/可跑
# 不改动系统，仅检测 + 在临时 venv 试装 Python 依赖，输出一份通过/失败清单。
# 用法： bash deploy/00_smoke_test.sh
# 建议先跑 01_install_system_deps.sh 再跑本脚本。
# ============================================================
set -uo pipefail   # 不用 -e：本脚本要把每项失败都记录下来而非中断

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
REQ="$ROOT/backend/requirements-server.txt"

PASS=0; FAIL=0
ok()   { echo "  [ OK ] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
note() { echo "  [ -- ] $1"; }

echo "================ 系统工具检测 ================"
# Python 版本（要求 >= 3.8）
if command -v python3 >/dev/null 2>&1; then
  PV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
  if python3 -c 'import sys;exit(0 if sys.version_info[:2]>=(3,8) else 1)'; then
    ok "python3 $PV (>=3.8)"
  else
    bad "python3 $PV 过低，需 >=3.8"
  fi
else
  bad "未安装 python3"
fi

for t in pip3 git nginx gcc make; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t 存在"; else bad "$t 缺失"; fi
done

# PostgreSQL（命令可能不在 PATH，多路径探测）
if command -v psql >/dev/null 2>&1 || ls /usr/pgsql-*/bin/psql >/dev/null 2>&1; then
  ok "PostgreSQL 客户端存在"
else
  note "未检测到 psql（若用 pg8000 + 远程库可忽略；本机库需装 postgresql-server）"
fi

# Rust（pydantic-core 无 wheel 时才需要）
if command -v cargo >/dev/null 2>&1; then ok "rust/cargo 存在（pydantic-core 可源码编译）"
else note "无 rust/cargo（若下方 pydantic 安装失败再装： dnf install -y rust cargo）"; fi

echo
echo "============ Python 依赖试装（临时 venv） ============"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if python3 -m venv "$TMP/venv" 2>/dev/null; then
  ok "创建 venv"
  # shellcheck disable=SC1091
  source "$TMP/venv/bin/activate"
  python -m pip install --upgrade pip >/dev/null 2>&1 && ok "升级 pip" || note "pip 升级失败（不致命）"

  echo "  正在试装 $REQ ……（联网，耗时数分钟）"
  if pip install -r "$REQ" > "$TMP/pip.log" 2>&1; then
    ok "requirements-server.txt 全部安装成功"
  else
    bad "部分依赖安装失败，详见： $TMP/pip.log（关键行如下）"
    grep -iE "error|failed building|no matching distribution|cargo|rust" "$TMP/pip.log" | tail -n 15 | sed 's/^/      /'
    echo "      （临时目录退出即删，可先 cp $TMP/pip.log /root/ 留存）"
    cp "$TMP/pip.log" /root/pip-smoke.log 2>/dev/null && echo "      已复制到 /root/pip-smoke.log"
  fi

  echo "  逐个 import 关键模块："
  for m in fastapi uvicorn gunicorn pydantic pydantic_settings sqlalchemy pg8000 jwt httpx; do
    if python -c "import $m" 2>/dev/null; then ok "import $m"; else bad "import $m 失败"; fi
  done

  # 可选项：PyMuPDF（PDF 解析）/ fastembed（本地嵌入），失败不影响主链路
  echo "  可选依赖（失败不影响主功能）："
  pip install "PyMuPDF==1.24.1" >/dev/null 2>&1 && python -c "import fitz" 2>/dev/null \
    && ok "PyMuPDF 可用（PDF 手册导入可用）" || note "PyMuPDF 不可用 → PDF 导入将禁用，用纯文本案例录入"
  deactivate
else
  bad "无法创建 venv（检查 python3-venv / python3 完整性）"
fi

echo
echo "================ pgvector（可选优化）================"
if command -v pg_config >/dev/null 2>&1 || ls /usr/pgsql-*/bin/pg_config >/dev/null 2>&1; then
  note "存在 pg_config，可尝试编译 pgvector（bash deploy/02_install_pgvector.sh）"
else
  note "无 pg_config（缺 postgresql-devel）。pgvector 为可选优化——不装也能用 JSON+内存余弦跑通"
fi

echo
echo "==================== 结论 ===================="
echo "  通过 $PASS 项，失败 $FAIL 项。"
if [[ $FAIL -eq 0 ]]; then
  echo "  ✅ 依赖冒烟全部通过，可继续 02~05 部署。"
else
  echo "  ⚠️  存在失败项，请按 deploy/README.md「LoongArch 排雷」逐项处理后重试。"
fi
