"""数据库会话与基类。

开发期用 SQLite；生产将 DATABASE_URL 改为 PostgreSQL+pgvector 即可。
向量在 SQLite 下以 JSON 文本存储、Python 内存计算余弦；
迁移到 pgvector 后改为 vector 列 + SQL 近邻检索（见部署文档）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
