"""知识图谱路由（M4）：图数据（ECharts）+ 节点溯源（相关案例与相邻实体）。"""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import (
    KGEntity, KGEntityAlias, KGRelation, KGRelationEvidence, RepairCase, User,
)
from ..schemas import (
    KGCaseBrief, KGEntityCases, KGGraph, KGLink, KGNode,
    ReasoningChainResp,
)
from ..rag.graph_rag import fault_tree, reasoning_chain, reasoning_chain_with_confidence

router = APIRouter(prefix="/api/kg", tags=["kg"])


@router.get("/relations/{rid}/evidence")
def relation_evidence(
    rid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return provenance, review state and aliases for one graph relation."""
    relation = db.get(KGRelation, rid)
    if not relation:
        raise HTTPException(404, "知识图谱关系不存在")
    src = db.get(KGEntity, relation.src_id)
    dst = db.get(KGEntity, relation.dst_id)
    evidence = db.execute(
        select(KGRelationEvidence)
        .where(KGRelationEvidence.relation_id == rid)
        .order_by(KGRelationEvidence.version.desc())
    ).scalars().all()
    entity_ids = [relation.src_id, relation.dst_id]
    aliases = db.execute(
        select(KGEntityAlias).where(KGEntityAlias.entity_id.in_(entity_ids))
    ).scalars().all()
    return {
        "relation": {
            "id": relation.id,
            "source": src.name if src else "",
            "type": relation.rel_type,
            "target": dst.name if dst else "",
        },
        "evidence": [
            {
                "source_case_id": item.source_case_id,
                "evidence_text": item.evidence_text,
                "extraction_method": item.extraction_method,
                "confidence": item.confidence,
                "review_status": item.review_status,
                "version": item.version,
            }
            for item in evidence
        ],
        "aliases": [
            {
                "entity_id": item.entity_id,
                "alias": item.alias,
                "method": item.normalization_method,
            }
            for item in aliases
        ],
    }


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


@router.get("/reasoning", response_model=ReasoningChainResp)
def get_reasoning_chain(
    query: str = Query(..., description="故障描述或关键词"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识图谱推理链（G10）：从故障实体出发，推理出 故障→原因→措施 完整链路。

    与 /graph 的区别：/graph 返回全图拓扑，/reasoning 返回有向推理路径，
    前端可可视化为"诊断推理链"——直观展示系统如何从故障现象推理到处理措施。
    """
    chains = reasoning_chain(db, query)
    return ReasoningChainResp(query=query, chains=chains, total=len(chains))


@router.get("/fault_tree")
def get_fault_tree(
    query: str = Query(..., description="故障描述或关键词"),
    max_depth: int = Query(3, description="最大推理深度", ge=1, le=5),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """故障树分析（FTA · G10+）：从故障实体出发，自动构建故障树结构。

    返回嵌套树形结构，每个节点含 name/type/confidence/measures/children，
    可信度沿路径深度衰减（0.85^depth），前端可用 ECharts 树图可视化。

    与 /reasoning 的区别：/reasoning 返回扁平链路列表，
    /fault_tree 返回层次化树结构，适合树形可视化与深度分析。
    """
    result = fault_tree(db, query, max_depth=max_depth)
    if not result:
        raise HTTPException(404, "知识图谱中未找到匹配的故障实体")
    return result


@router.get("/reasoning_confidence")
def get_reasoning_with_confidence(
    query: str = Query(..., description="故障描述或关键词"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """带可信度的推理链（G10+）：每条链含置信度与跳数。"""
    chains = reasoning_chain_with_confidence(db, query)
    return {"query": query, "chains": chains, "total": len(chains)}
