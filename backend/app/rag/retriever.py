"""检索器：向量召回 + 混合重排（增强 G8）+ 设备型号结构化过滤。

流程：先用向量余弦召回较多候选（top_k×3），再做二次重排——
融合「语义相似度」与「字面词项重叠（中文 bigram + 英文/数字词）」重新打分，
弥补纯向量在专有名词/型号上的不足，提升引用准确率。纯 Python、零依赖。

开发期(SQLite)：把候选分块的向量取到内存算余弦。
生产(pgvector)：向量召回可改为 SQL 近邻检索，重排逻辑不变（见部署文档）。
"""
import math
import re
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..embedding import get_embedder
from ..models import DocChunk, Document

# 重排融合权重与召回倍数
_VEC_WEIGHT = 0.7
_LEX_WEIGHT = 0.3
_RECALL_MULT = 3
_RECALL_MIN = 12

_CJK_RE = re.compile(r"[一-鿿]")
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _terms(text: str) -> set:
    """词项集合：中文相邻字 bigram + 英文/数字词（小写）。"""
    chars = _CJK_RE.findall(text)
    terms = set(a + b for a, b in zip(chars, chars[1:]))
    terms |= set(w.lower() for w in _WORD_RE.findall(text))
    return terms


def _lexical(q_terms: set, content: str) -> float:
    """字面重叠：命中的查询词项占比（0~1）。"""
    if not q_terms:
        return 0.0
    inter = len(q_terms & _terms(content))
    return inter / len(q_terms)


def retrieve(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    top_k: Optional[int] = None,
) -> List[dict]:
    top_k = top_k or settings.retrieve_top_k
    recall_k = max(top_k * _RECALL_MULT, _RECALL_MIN)
    qvec = get_embedder().embed_one(query)

    stmt = select(DocChunk, Document).join(Document, DocChunk.doc_id == Document.id)
    stmt = stmt.where(Document.status == "approved")
    if device_model:
        stmt = stmt.where(Document.device_model == device_model)

    rows = db.execute(stmt).all()

    # 第一阶段：向量召回
    scored = []
    for chunk, doc in rows:
        if not chunk.embedding:
            continue
        vec = _cosine(qvec, chunk.embedding)
        scored.append((vec, chunk, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = scored[:recall_k]

    # 第二阶段：混合重排（语义 + 字面）
    q_terms = _terms(query)
    reranked = []
    for vec, chunk, doc in candidates:
        lex = _lexical(q_terms, chunk.content)
        final = vec * _VEC_WEIGHT + lex * _LEX_WEIGHT
        reranked.append((final, vec, lex, chunk, doc))
    reranked.sort(key=lambda x: x[0], reverse=True)

    results = []
    for final, vec, lex, chunk, doc in reranked[:top_k]:
        results.append({
            "chunk_id": chunk.id,
            "doc_id": doc.id,
            "doc_title": doc.title,
            "device_model": doc.device_model,
            "page": chunk.page,
            "content": chunk.content,
            "score": round(float(final), 4),
            "vec_score": round(float(vec), 4),
            "lex_score": round(float(lex), 4),
        })
    return results
