# ====================================================================
# 前端镜像：多阶段构建
#   阶段 1：node:20-alpine 编译 Vue3 生产包
#   阶段 2：nginx:alpine 托管静态文件并反代后端
#
# 注意：build context 为项目根目录（见 docker-compose.yml），
# 因此 COPY 路径均带 frontend/ 前缀，使根目录的 .dockerignore 生效。
# ====================================================================

# ─── 阶段 1：构建 ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# 利用层缓存：先复制依赖清单再装包
COPY frontend/package.json frontend/package-lock.json* ./
# 优先 npm ci（按 lock 文件精确安装），失败则回退 npm install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 复制源码并构建，产物输出到 dist/
COPY frontend/ ./
RUN npm run build

# ─── 阶段 2：运行 ─────────────────────────────────────────
FROM nginx:alpine

# 替换 nginx 默认站点配置
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段拷贝产物到 nginx 静态目录
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
