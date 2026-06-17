"""FastAPI 应用入口。"""
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .db import Base, engine
from . import models  # noqa: F401  确保模型注册到 Base
from .metrics import record_request, render
from .routers import (
    auth, chat, documents, sop, cases, kg, feedback, devices, dashboard, alert,
    audit,
)

app = FastAPI(
    title="设备检修知识检索与作业系统 API",
    description="基于多模态大模型技术 · 第十五届中国软件杯 A组",
    version="0.6.0",
)

# 开发期放开 CORS；生产由 Nginx 同源反代，可收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """可观测性：记录每个接口的请求数与延迟（按路由模板归并，避免 ID 高基数）。"""
    start = time.perf_counter()
    response = await call_next(request)
    dur = time.perf_counter() - start
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    record_request(request.method, path, response.status_code, dur)
    return response


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health():
    return {"status": "ok", "stage": "M5+"}


@app.get("/metrics")
def metrics():
    """Prometheus 抓取端点（纯文本曝露格式）。"""
    return PlainTextResponse(render(), media_type="text/plain; version=0.0.4; charset=utf-8")


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(sop.router)
app.include_router(cases.router)
app.include_router(kg.router)
app.include_router(feedback.router)
app.include_router(devices.router)
app.include_router(dashboard.router)
app.include_router(alert.router)
app.include_router(audit.router)
