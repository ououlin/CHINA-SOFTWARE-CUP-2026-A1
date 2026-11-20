# ====================================================================
# 后端镜像：FastAPI + uvicorn
# 基于 python:3.12-slim 保持精简，仅在需要时安装编译工具与运行库
#
# 注意：build context 为项目根目录（见 docker-compose.yml），
# 因此 COPY 路径均带 backend/ 前缀，使根目录的 .dockerignore 生效。
# ====================================================================
FROM python:3.12-slim

# 环境变量：禁用输出缓冲 / .pyc 缓存 / pip 缓存，统一时区与编码
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8

WORKDIR /app

# 安装系统依赖：
#   - gcc g++ make：编译 C 扩展（部分 wheel 不可用时兜底）
#   - libglib2.0-0 libsm6 libxrender1 libxext6：PyMuPDF 运行所需
#   - curl ca-certificates：容器健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ make \
        libglib2.0-0 libsm6 libxrender1 libxext6 \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，利用 Docker 层缓存（依赖变动少时构建更快）
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

# 复制后端源码（仅 backend/ 子目录）
COPY backend/ ./

# 暴露 FastAPI 服务端口
EXPOSE 8000

# 健康检查：每 30s 探测 /api/health，启动预留 30s（fastembed 首启可能较慢）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# 使用 uvicorn 启动应用（app.main:app，对应 backend/app/main.py 中的 app 实例）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
