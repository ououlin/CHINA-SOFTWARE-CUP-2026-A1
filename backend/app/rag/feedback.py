"""反馈增强：召回与当前问题相似的"已确认人工修正"，注入到后续回答上下文。

这是 M5 闭环优化的核心——用户对历史回答的纠正会沉淀为修正知识，
当再次遇到相似问题时优先采纳，提升系统适配性。
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..embedding import get_embedder
from ..models import LLMFeedback
from .retriever import _cosine

# 相似度阈值：bge-small-zh 下同/近义问题余弦通常 >0.85，取 0.82 兼顾召回与精度
CORRECTION_THRESHOLD = 0.82
CORRECTION_TOP_K = 2


def retrieve_corrections(
    db: Session,
    query: str,
    user_id: Optional[int] = None,
    top_k: int = CORRECTION_TOP_K,
    threshold: float = CORRECTION_THRESHOLD,
) -> List[dict]:
    """返回与 query 最相似的生效人工修正（影子知识库流控）。

    全局只注入 pub_status=published 的修正；提交者本人额外可见自己 pending_review
    的修正（用于"自己纠错实时预览"），不影响他人，防范错误/恶意标注污染全局。
    """
    rows = db.execute(
        select(LLMFeedback).where(
            LLMFeedback.status == "active",
            LLMFeedback.correction_text != "",
        )
    ).scalars().all()

    def _visible(r) -> bool:
        ps = getattr(r, "pub_status", "published")
        if ps == "published":
            return True
        if user_id and ps == "pending_review" and r.user_id == user_id:
            return True
        return False

    rows = [r for r in rows if r.query_embedding and _visible(r)]
    if not rows:
        return []

    qvec = get_embedder().embed_one(query)
    scored = []
    for r in rows:
        s = _cosine(qvec, r.query_embedding)
        if s >= threshold:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": r.id,
            "query": r.query,
            "correction_text": r.correction_text,
            "score": round(float(s), 4),
        }
        for s, r in scored[:top_k]
    ]
