"""PostgreSQL/pgvector retrieval contract and optional integration tests."""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import Session

import app.rag.retriever as retriever
from app.config import settings
from app.db import Base
from app.models import DocChunk, Document


def test_embedding_column_uses_dialect_specific_type():
    pg_ddl = str(CreateTable(DocChunk.__table__).compile(dialect=postgresql.dialect()))
    sqlite_ddl = str(CreateTable(DocChunk.__table__).compile(dialect=sqlite.dialect()))
    assert f"VECTOR({settings.embedding_dim})" in pg_ddl
    assert "JSON" in sqlite_ddl


class _EmptyMappings:
    def mappings(self):
        return self

    def all(self):
        return []


class _RecordingDB:
    def __init__(self):
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _EmptyMappings()


def test_postgres_query_contains_vector_trigram_and_rrf():
    db = _RecordingDB()
    retriever._retrieve_postgres(
        db, "主轴异响", [0.1] * settings.embedding_dim, None, 4,
    )
    sql = str(db.statement)
    assert "<=>" in sql
    assert "similarity(" in sql
    assert "rrf_score" in sql
    # RRF 权重与 k 必须显式转 double precision：否则 pg8000 以文本发送 1.0，
    # PostgreSQL 会把参数推导成 bigint 并报 invalid input syntax for type bigint。
    assert "CAST(:use_vector AS double precision)" in sql
    assert "CAST(:rrf_k AS double precision)" in sql
    assert "has_partial_match" in sql
    assert "content % :query" not in sql
    assert db.params["top_k"] == 4


def test_pgvector_migration_uses_configurable_dimension():
    migration = (
        Path(__file__).resolve().parents[2] / "deploy" / "03_migrate_pgvector.sql"
    ).read_text(encoding="utf-8")
    assert "vector(:embedding_dim)" in migration
    assert "vector(512)" not in migration
    assert "vector_dimension_matches" in migration


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL is required for pgvector integration",
)
def test_pgvector_hybrid_retrieval_in_real_postgres(monkeypatch):
    engine = create_engine(os.environ["TEST_POSTGRES_URL"], future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)

    marker = f"ci-pgvector-{uuid.uuid4().hex}"
    relevant = [1.0] + [0.0] * (settings.embedding_dim - 1)
    irrelevant = [0.0, 1.0] + [0.0] * (settings.embedding_dim - 2)

    class FixedEmbedder:
        def embed_one(self, value):
            return relevant

    monkeypatch.setattr(retriever, "get_embedder", lambda: FixedEmbedder())
    monkeypatch.setattr(settings, "vector_backend", "pgvector")
    monkeypatch.setattr(settings, "parent_child_enabled", False)

    with Session(engine) as db:
        doc = Document(title=marker, status="approved", device_model="CNC-01")
        other = Document(title=f"{marker}-other", status="approved", device_model="CNC-01")
        db.add_all([doc, other])
        db.flush()
        db.add_all([
            DocChunk(
                doc_id=doc.id, page=1,
                content="主轴轴承异响，应检查滚道剥落与润滑状态。",
                embedding=relevant,
            ),
            DocChunk(
                doc_id=other.id, page=1,
                content="液压油温正常，系统无异常。",
                embedding=irrelevant,
            ),
        ])
        db.commit()

        results = retriever.retrieve(db, "主轴异响", device_model="CNC01", top_k=2)
        assert results
        assert results[0]["doc_title"] == marker
        assert results[0]["retrieval_method"] == "pgvector_trgm_rrf:hybrid"

        db.delete(doc)
        db.delete(other)
        db.commit()
