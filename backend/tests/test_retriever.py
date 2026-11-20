"""检索候选集和消融模式回归测试。"""

from app.config import settings
from app.models import DocChunk, Document
from app.rag.retriever import _load_filtered_chunks, retrieve


class _EmptyResult:
    def all(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _EmptyResult()


def test_candidate_query_is_not_truncated_before_scoring():
    """向量评分前不得用任意 LIMIT 丢弃知识分块。"""
    db = _RecordingSession()
    _load_filtered_chunks(db, None)
    assert len(db.statements) == 1
    assert " LIMIT " not in f" {db.statements[0]} ".upper()


def test_hybrid_mode_keeps_lexical_only_chunk(db_session, monkeypatch):
    doc = Document(title="无向量手册", status="approved", device_model="CNC-01")
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocChunk(
        doc_id=doc.id,
        page=1,
        content="专有故障码 ZXQ-9988 应检查主轴编码器。",
        embedding=None,
    ))
    db_session.commit()

    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    monkeypatch.setattr(settings, "parent_child_enabled", False)
    results = retrieve(db_session, "ZXQ-9988", device_model="CNC01", top_k=3)

    assert results
    assert results[0]["doc_title"] == "无向量手册"
    assert results[0]["lex_score"] > 0
    assert results[0]["retrieval_method"] == "python_rrf:hybrid"


def test_retrieval_ablation_modes_are_reported(db_session, monkeypatch):
    monkeypatch.setattr(settings, "parent_child_enabled", False)
    for mode in ("vector", "lexical", "hybrid"):
        monkeypatch.setattr(settings, "retrieval_mode", mode)
        results = retrieve(db_session, "怠速不稳", top_k=2)
        assert results
        assert all(r["retrieval_method"] == f"python_rrf:{mode}" for r in results)
        assert all("rrf_score" in r for r in results)
