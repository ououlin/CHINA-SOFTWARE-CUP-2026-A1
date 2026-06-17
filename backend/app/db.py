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


def ensure_schema():
    """轻量迁移：为已存在的表补齐新增列（SQLite / PG 均支持 ADD COLUMN）。

    create_all 只新建缺失的表、不会给旧表加列；本函数补齐影子知识库的
    pub_status / version 列，使老库平滑升级（已有修正默认置为 published 保持原行为）。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = insp.get_table_names()
    if "llm_feedbacks" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("llm_feedbacks")}
    alters = []
    if "pub_status" not in cols:
        alters.append("ALTER TABLE llm_feedbacks ADD COLUMN pub_status VARCHAR(16) DEFAULT 'published'")
    if "version" not in cols:
        alters.append("ALTER TABLE llm_feedbacks ADD COLUMN version INTEGER DEFAULT 1")
    if alters:
        with engine.begin() as conn:
            for a in alters:
                conn.execute(text(a))
