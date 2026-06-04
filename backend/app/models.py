"""ORM 模型（M1 核心表）。

M1 仅落地：用户、文档、文档分块（含向量）、问答日志。
M3~M5 的 SOP 模板、知识图谱、反馈表后续阶段补充。
"""
import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship

from .db import Base


def _now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(64), default="")
    hashed_password = Column(String(256), nullable=False)
    # worker 一线人员 / auditor 审核员 / admin 管理员
    role = Column(String(16), default="worker", nullable=False)
    created_at = Column(DateTime, default=_now)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False)
    source_type = Column(String(32), default="manual")  # manual 手册 / case 案例
    device_model = Column(String(128), default="", index=True)  # 设备型号（结构化过滤）
    device_type = Column(String(128), default="", index=True)   # 设备类型
    file_path = Column(String(512), default="")
    status = Column(String(16), default="approved")  # pending / approved
    created_at = Column(DateTime, default=_now)

    chunks = relationship("DocChunk", back_populates="document",
                          cascade="all, delete-orphan")


class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    page = Column(Integer, default=0)
    # 开发期(SQLite)：以 JSON 数组存向量；生产(pgvector)：替换为 vector 列
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)

    document = relationship("Document", back_populates="chunks")


class QALog(Base):
    __tablename__ = "qa_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    query = Column(Text, nullable=False)
    modality = Column(String(16), default="text")  # text / image / model
    answer = Column(Text, default="")
    citations = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)
