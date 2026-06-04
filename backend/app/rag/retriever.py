"""检索器：向量相似度 + 设备型号结构化过滤（混合检索雏形）。

开发期(SQLite)：把候选分块的向量取到内存算余弦。
生产(pgvector)：改为 `ORDER BY embedding <=> :qvec LIMIT k` 的 SQL 近邻检索，
接口签名不变（见部署文档的迁移说明）。
"""
import math
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..embedding import get_embedder
from ..models import DocChunk, Document


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def retrieve(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    top_k: Optional[int] = None,
) -> List[dict]:
    top_k = top_k or settings.retrieve_top_k
    qvec = get_embedder().embed_one(query)

    stmt = select(DocChunk, Document).join(Document, DocChunk.doc_id == Document.id)
    stmt = stmt.where(Document.status == "approved")
    if device_model:
        stmt = stmt.where(Document.device_model == device_model)

    rows = db.execute(stmt).all()
    scored = []
    for chunk, doc in rows:
        if not chunk.embedding:
            continue
        score = _cosine(qvec, chunk.embedding)
        scored.append((score, chunk, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, chunk, doc in scored[:top_k]:
        results.append({
            "chunk_id": chunk.id,
            "doc_id": doc.id,
            "doc_title": doc.title,
            "device_model": doc.device_model,
            "page": chunk.page,
            "content": chunk.content,
            "score": round(float(score), 4),
        })
    return results
