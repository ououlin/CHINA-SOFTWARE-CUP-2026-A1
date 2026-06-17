"""Graph RAG（进阶）：在向量检索之外，从知识图谱补充结构化上下文。

当用户查询命中图谱中的实体（设备 / 部件 / 故障），取其邻居关系（关联故障、
原因、措施）作为三元组一并喂给大模型，让回答兼具"文本片段"与"结构化关联"，
彰显技术深度。纯关系表查询，零额外依赖。
"""
from typing import List, Optional

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..models import KGEntity, KGRelation


def graph_context(db: Session, query: str,
                  contexts: Optional[List[dict]] = None,
                  max_edges: int = 12) -> List[str]:
    """返回命中图谱实体的邻居三元组文本（如「怠速不稳 —源于→ 化油器堵塞」）。

    在「查询 + 检索到的相关片段」组成的文本里匹配实体名——比仅匹配查询更鲁棒：
    口语化/改写后的查询未必含规范实体名，但召回的相关片段几乎必然提及。
    """
    haystack = query or ""
    if contexts:
        haystack += " " + " ".join(c.get("content", "") for c in contexts)
    if not haystack.strip():
        return []

    entities = db.execute(select(KGEntity)).scalars().all()
    id2name = {e.id: e.name for e in entities}
    # 命中：实体名（≥2字，避免噪音）作为子串出现在「查询 + 片段」中
    hit_ids = {e.id for e in entities if len(e.name) >= 2 and e.name in haystack}
    if not hit_ids:
        return []

    rels = db.execute(
        select(KGRelation).where(
            or_(KGRelation.src_id.in_(hit_ids), KGRelation.dst_id.in_(hit_ids)))
    ).scalars().all()

    lines: List[str] = []
    seen = set()
    for r in rels:
        s, d = id2name.get(r.src_id), id2name.get(r.dst_id)
        if not s or not d:
            continue
        key = (s, r.rel_type, d)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{s} —{r.rel_type}→ {d}")
        if len(lines) >= max_edges:
            break
    return lines
