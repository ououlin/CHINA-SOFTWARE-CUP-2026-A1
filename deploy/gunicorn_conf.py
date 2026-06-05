"""Gunicorn 生产配置（配合 Uvicorn 异步 worker 跑 FastAPI）。

启动： gunicorn -c deploy/gunicorn_conf.py app.main:app
（工作目录须为 backend/，由 systemd 单元设置）
"""
import os

# 仅监听本机，由 Nginx 反向代理对外暴露
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")

# Uvicorn 异步 worker：单 worker 即可处理大量并发（SSE 长连接 + 等待云端 API 为主）。
# 多 worker 时注意：开发期 SQLite 不适合多进程并发写；用 PostgreSQL 可适当加大。
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "uvicorn.workers.UvicornWorker"

# SSE 流式问答 + 云端大模型生成较慢，超时取大，避免长连接被误杀
timeout = int(os.getenv("GUNICORN_TIMEOUT", "300"))
graceful_timeout = 30
keepalive = 5

# 日志输出到 stdout/stderr，交由 systemd journald 收集
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
proc_name = "device-repair-backend"
