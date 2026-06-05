#!/usr/bin/env bash
# ============================================================
# 01 安装系统依赖（银河麒麟高级服务器版 / LoongArch，RHEL 系 dnf/yum）
# 需 root： sudo bash deploy/01_install_system_deps.sh
# 幂等：可重复执行。
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "请用 root 运行： sudo bash $0" >&2
  exit 1
fi

# 选择包管理器（麒麟 V10/V11 一般有 dnf；否则 yum）
if command -v dnf >/dev/null 2>&1; then PM=dnf; else PM=yum; fi
echo "==> 使用包管理器：$PM"

# 关键依赖（缺一不可）
CORE_PKGS=(python3 python3-pip git nginx)
# 数据库（PostgreSQL 服务端 + 扩展包）
DB_PKGS=(postgresql-server postgresql-contrib)
# 编译类（pydantic-core 若需源码编译、或自行编译 PyMuPDF/pgvector 时用到）
BUILD_PKGS=(python3-devel gcc gcc-c++ make tar)

echo "==> 安装核心依赖：${CORE_PKGS[*]}"
$PM install -y "${CORE_PKGS[@]}"

echo "==> 安装数据库：${DB_PKGS[*]}"
$PM install -y "${DB_PKGS[@]}" || echo "[警告] PostgreSQL 包名在本系统可能不同，请对照麒麟源手动安装"

echo "==> 安装编译工具：${BUILD_PKGS[*]}"
$PM install -y "${BUILD_PKGS[@]}" || echo "[警告] 部分编译工具安装失败，按需排查"

# 可选：pgvector 源码编译需要 PostgreSQL 开发头文件
$PM install -y postgresql-devel || echo "[提示] postgresql-devel 未装（仅编译 pgvector 时需要）"

# 可选：若 pydantic-core 在 LoongArch 无 wheel，需 Rust 工具链让 pip 自行编译
if ! command -v cargo >/dev/null 2>&1; then
  echo "[提示] 未检测到 Rust(cargo)。如 04 步 pip 安装 pydantic-core 失败，再执行： $PM install -y rust cargo"
fi

echo
echo "==> 版本核对："
python3 --version || true
python3 -m pip --version || true
nginx -v 2>&1 || true
( command -v postgres >/dev/null 2>&1 && postgres --version ) || echo "postgres: 未在 PATH（通常在 /usr/bin 或 /usr/pgsql-*/bin）"
echo
echo "完成。下一步：bash deploy/00_smoke_test.sh 评估 Python 依赖可装性。"
