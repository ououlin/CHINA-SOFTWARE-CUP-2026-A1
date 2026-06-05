"""知识图谱落库：实体按 (name, etype) 去重 upsert，关系保留来源案例。

被 routers/cases.py（审核通过后）与 seed.py（种子案例）共用。
"""
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KGEntity, KGRelation


def upsert_entity(db: Session, name: str, etype: str) -> KGEntity:
    """按 (name, etype) 查找，存在则复用（跨案例共享节点），否则新建。"""
    e = db.execute(
        select(KGEntity).where(KGEntity.name == name, KGEntity.etype == etype)
    ).scalar_one_or_none()
    if e:
        return e
    e = KGEntity(name=name, etype=etype)
    db.add(e)
    db.flush()
    return e


def persist_extraction(
    db: Session, case_id: int, extracted: Dict[str, List[dict]]
) -> Tuple[int, int]:
    """把抽取结果落库；返回 (实体数, 关系数)。调用方负责 commit。"""
    name_to_id: Dict[str, int] = {}
    for ent in extracted.get("entities", []):
        e = upsert_entity(db, ent["name"], ent["etype"])
        name_to_id[ent["name"]] = e.id

    rel_count = 0
    for r in extracted.get("relations", []):
        sid = name_to_id.get(r["source"])
        did = name_to_id.get(r["target"])
        if not sid or not did:
            continue
        db.add(KGRelation(src_id=sid, rel_type=r.get("rel", "相关"),
                          dst_id=did, source_case_id=case_id))
        rel_count += 1
    db.flush()
    return len(name_to_id), rel_count
