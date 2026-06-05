#!/usr/bin/env bash
# ============================================================
# 05 部署前端静态资源 + 配置 Nginx（反代后端 + SSE 透传）
# 需 root： sudo bash deploy/05_deploy_frontend.sh
#
# 前置：前端在【开发机(Windows)】构建后产物拷到服务器：
#   开发机:  cd frontend && npm run build      # 生成 frontend/dist
#   拷贝:    scp -r frontend/dist  root@<server>:/opt/device-repair/frontend/
# （之所以不在 LoongArch 上构建：Node 工具链在龙芯上亦有风险，按方案"前端在
#   Windows 编译成静态文件、服务器只跑 Nginx"，最稳。）
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "请用 root 运行： sudo bash $0" >&2; exit 1; fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
DIST="$ROOT/frontend/dist"

if [[ ! -f "$DIST/index.html" ]]; then
  echo "未找到前端构建产物 $DIST/index.html。" >&2
  echo "请在开发机执行 npm run build 并把 frontend/dist 拷到此处后重试。" >&2
  exit 1
fi

# 1) 安装站点配置（按实际仓库根替换路径）
echo "==> 写入 Nginx 站点配置"
CONF=/etc/nginx/conf.d/device-repair.conf
sed "s#/opt/device-repair#$ROOT#g" "$HERE/nginx/device-repair.conf" > "$CONF"

# 2) SELinux（麒麟默认常为 enforcing）：放开反代联网 + 修正静态目录上下文
if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
  echo "==> SELinux 处理：允许 nginx 反代联网，修正静态目录上下文"
  setsebool -P httpd_can_network_connect 1 || echo "[提示] setsebool 失败，可手动处理"
  command -v restorecon >/dev/null 2>&1 && restorecon -R "$ROOT/frontend/dist" || true
fi

# 3) 防火墙放行 80（如启用 firewalld）
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  echo "==> 放行 80/tcp"
  firewall-cmd --permanent --add-service=http >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
fi

# 4) 校验并重载
echo "==> nginx -t 校验配置"
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx || systemctl restart nginx

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "✅ 前端部署完成。浏览器访问： http://${IP:-<服务器IP>}/"
echo "   演示账号：worker/worker123 、auditor/auditor123 、admin/admin123"
