"""知识图谱路由（M4）：图数据（ECharts）+ 节点溯源（相关案例与相邻实体）。"""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import KGEntity, KGRelation, RepairCase, User
from ..schemas import (
    KGCaseBrief, KGEntityCases, KGGraph, KGLink, KGNode,
)

router = APIRouter(prefix="/api/kg", tags=["kg"])


def _node(e: KGEntity, degree: int = 0) -> KGNode:
    return KGNode(id=e.id, name=e.name, etype=e.etype, degree=degree)


@router.get("/graph", response_model=KGGraph)
def get_graph(
    device_model: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回整张知识图谱（可选按来源案例的设备型号过滤）。"""
    rels = db.execute(select(KGRelation)).scalars().all()

    if device_model:
        allowed = {
            c.id for c in db.execute(
                select(RepairCase).where(RepairCase.device_model == device_model)
            ).scalars().all()
        }
        rels = [r for r in rels if r.source_case_id in allowed]

    # 关系按 (src, rel, dst) 去重用于展示
    seen, links = set(), []
    degree = defaultdict(int)
    for r in rels:
        key = (r.src_id, r.rel_type, r.dst_id)
        if key in seen:
            continue
        seen.add(key)
        links.append(KGLink(source=r.src_id, target=r.dst_id, rel=r.rel_type))
        degree[r.src_id] += 1
        degree[r.dst_id] += 1

    entities = db.execute(select(KGEntity)).scalars().all()
    if device_model:
        used = {ln.source for ln in links} | {ln.target for ln in links}
        entities = [e for e in entities if e.id in used]

    stats = defaultdict(int)
    nodes = []
    for e in entities:
        nodes.append(_node(e, degree.get(e.id, 0)))
        stats[e.etype] += 1

    return KGGraph(nodes=nodes, links=links, stats=dict(stats))


@router.get("/entities/{eid}/cases", response_model=KGEntityCases)
def entity_cases(eid: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """点击节点：返回该实体相关的案例（溯源）与直接相邻实体。"""
    e = db.get(KGEntity, eid)
    if not e:
        raise HTTPException(404, "实体不存在")

    rels = db.execute(
        select(KGRelation).where(
            (KGRelation.src_id == eid) | (KGRelation.dst_id == eid)
        )
    ).scalars().all()

    case_ids, neighbor_ids = set(), set()
    for r in rels:
        if r.source_case_id:
            case_ids.add(r.source_case_id)
        neighbor_ids.add(r.dst_id if r.src_id == eid else r.src_id)

    cases = []
    if case_ids:
        rows = db.execute(
            select(RepairCase).where(RepairCase.id.in_(case_ids))
            .order_by(RepairCase.id.desc())
        ).scalars().all()
        cases = [
            KGCaseBrief(id=c.id, title=c.title, device_model=c.device_model,
                        status=c.status)
            for c in rows
        ]

    neighbors = []
    if neighbor_ids:
        rows = db.execute(
            select(KGEntity).where(KGEntity.id.in_(neighbor_ids))
        ).scalars().all()
        neighbors = [_node(n) for n in rows]

    return KGEntityCases(entity=_node(e), cases=cases, neighbors=neighbors)
