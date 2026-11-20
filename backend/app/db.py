"""数据库会话与基类。

开发期用 SQLite；生产将 DATABASE_URL 改为 PostgreSQL+pgvector 即可。
向量在 SQLite 下以 JSON 文本存储、Python 内存计算余弦；
迁移到 pgvector 后改为 vector 列 + SQL 近邻检索（见部署文档）。
"""
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def uses_pgvector() -> bool:
    return (
        engine.dialect.name == "postgresql"
        and settings.vector_backend in ("auto", "pgvector")
    )


def prepare_database_features() -> None:
    """Enable PostgreSQL extensions required by hybrid retrieval before table creation."""
    if not uses_pgvector():
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception as exc:
        raise RuntimeError(
            "无法启用 PostgreSQL vector/pg_trgm 扩展；请用数据库管理员执行部署迁移脚本"
        ) from exc


def ensure_retrieval_schema() -> None:
    """Validate the vector column and create production retrieval indexes."""
    if not uses_pgvector():
        return
    with engine.begin() as conn:
        embedding_type = conn.execute(text("""
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = 'doc_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
        """)).scalar_one_or_none()
        expected_type = f"vector({settings.embedding_dim})"
        if embedding_type != expected_type:
            raise RuntimeError(
                f"doc_chunks.embedding 类型为 {embedding_type!r}，期望 {expected_type}；"
                "请核对 EMBEDDING_DIM 后执行 deploy/03_migrate_pgvector.sql"
            )
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_doc_chunks_embedding_hnsw
            ON doc_chunks USING hnsw (embedding vector_cosine_ops)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_doc_chunks_content_trgm
            ON doc_chunks USING gin (content gin_trgm_ops)
        """))


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
