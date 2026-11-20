"""知识图谱落库：实体按 (name, etype) 去重 upsert，关系保留来源案例。

被 routers/cases.py（审核通过后）与 seed.py（种子案例）共用。
"""
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .kg_align import align_extraction
from .models import (
    KGEntity, KGEntityAlias, KGRelation, KGRelationEvidence, RepairCase,
)


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
    db: Session, case_id: int, extracted: Dict[str, List[dict]], align: bool = True
) -> Tuple[int, int]:
    """把抽取结果落库；返回 (实体数, 关系数)。调用方负责 commit。

    align=True 时先做实体对齐消歧（把别名归一到已有标准节点）；
    种子手工 KG 已规范，传 align=False 跳过对齐、保持离线可种。
    """
    entities = extracted.get("entities", [])
    align_map = align_extraction(db, entities) if align else {}

    name_to_id: Dict[str, int] = {}
    for ent in entities:
        std_name = align_map.get(ent["name"], ent["name"])  # 对齐后的标准名
        e = upsert_entity(db, std_name, ent["etype"])
        name_to_id[ent["name"]] = e.id  # 原名→标准节点 id，供关系连边
        if ent["name"] != std_name:
            alias = db.execute(
                select(KGEntityAlias).where(
                    KGEntityAlias.entity_id == e.id,
                    KGEntityAlias.alias == ent["name"],
                )
            ).scalar_one_or_none()
            if not alias:
                db.add(KGEntityAlias(
                    entity_id=e.id,
                    alias=ent["name"],
                    normalization_method="entity_alignment",
                ))

    source_case = db.get(RepairCase, case_id)
    default_evidence = (source_case.content[:1000] if source_case else "")

    rel_count = 0
    for r in extracted.get("relations", []):
        sid = name_to_id.get(r["source"])
        did = name_to_id.get(r["target"])
        if not sid or not did:
            continue
        relation = KGRelation(
            src_id=sid, rel_type=r.get("rel", "相关"),
            dst_id=did, source_case_id=case_id,
        )
        db.add(relation)
        db.flush()
        confidence = r.get("confidence", 1.0 if not align else 0.75)
        db.add(KGRelationEvidence(
            relation_id=relation.id,
            source_case_id=case_id,
            evidence_text=(r.get("evidence") or default_evidence),
            extraction_method="manual_seed" if not align else "llm_aligned",
            confidence=max(0.0, min(1.0, float(confidence))),
            review_status="approved",
            version=1,
        ))
        rel_count += 1
    db.flush()
    return len(name_to_id), rel_count
