"""FastAPI 应用入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from . import models  # noqa: F401  确保模型注册到 Base
from .routers import auth, chat, documents, sop, cases, kg, feedback, devices

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


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health():
    return {"status": "ok", "stage": "M5+"}


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(sop.router)
app.include_router(cases.router)
app.include_router(kg.router)
app.include_router(feedback.router)
app.include_router(devices.router)
