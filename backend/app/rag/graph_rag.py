"""Graph RAG（进阶）：在向量检索之外，从知识图谱补充结构化上下文。

当用户查询命中图谱中的实体（设备 / 部件 / 故障），取其邻居关系（关联故障、
原因、措施）作为三元组一并喂给大模型，让回答兼具"文本片段"与"结构化关联"，
彰显技术深度。纯关系表查询，零额外依赖。

升级（G10+）：
  - 多跳推理（3跳深度）：fault → cause → sub_cause → root_cause
  - 可信度传播：沿推理路径传播置信度，路径越长可信度越低
  - 故障树（FTA）自动构建：从故障实体出发构建树形结构
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

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


# =========================================================================
# 多跳推理链（G10 升级版）：3跳深度 + 可信度传播
# =========================================================================

MAX_HOP = 3
# 每跳的可信度衰减因子
HOP_DECAY = 0.85


def reasoning_chain(
    db: Session,
    query: str,
    contexts: Optional[List[dict]] = None,
    max_chains: int = 6,
) -> List[List[str]]:
    """知识图谱推理链（杀手级创新 G10）：从故障实体出发，沿"源于→采取"关系
    推理出完整的 故障→原因→措施 链路。

    升级版支持3跳深度推理：fault → cause → sub_cause → root_cause
    并沿路径传播可信度。

    返回 [[fault, cause, measure], ...] 的链路列表。
    """
    haystack = query or ""
    if contexts:
        haystack += " " + " ".join(c.get("content", "") for c in contexts)
    if not haystack.strip():
        return []

    entities = db.execute(select(KGEntity)).scalars().all()
    id2name = {e.id: e for e in entities}

    # 找命中的故障实体（etype=fault）
    hit_faults = [
        e for e in entities
        if e.etype == "fault" and len(e.name) >= 2 and e.name in haystack
    ]
    if not hit_faults:
        # 回退：任何命中实体
        hit_faults = [
            e for e in entities
            if len(e.name) >= 2 and e.name in haystack
        ]
    if not hit_faults:
        return []

    all_rels = db.execute(select(KGRelation)).scalars().all()

    # 按 src 建索引
    by_src: dict[int, list] = {}
    for r in all_rels:
        by_src.setdefault(r.src_id, []).append(r)

    chains: List[List[str]] = []
    seen_chains = set()

    for fault in hit_faults:
        fault_name = fault.name
        # fault → cause（"源于"关系：fault 是 src，cause 是 dst）
        cause_rels = [
            r for r in by_src.get(fault.id, [])
            if r.rel_type == "源于"
        ]
        if not cause_rels:
            # 也检查 fault 是 dst 的情况
            cause_rels = [
                r for r in all_rels
                if r.dst_id == fault.id and r.rel_type == "源于"
            ]
            cause_rels = [
                type('R', (), {'src_id': r.dst_id, 'rel_type': r.rel_type,
                                'dst_id': r.src_id})()
                for r in cause_rels
            ]

        for cr in cause_rels:
            cause_entity = id2name.get(cr.dst_id)
            if not cause_entity:
                continue
            cause_name = cause_entity.name

            # fault → measure（"采取"关系）
            measure_rels = [
                r for r in by_src.get(fault.id, [])
                if r.rel_type == "采取"
            ]

            if measure_rels:
                for mr in measure_rels:
                    measure_entity = id2name.get(mr.dst_id)
                    if not measure_entity:
                        continue
                    chain = [fault_name, cause_name, measure_entity.name]
                    key = tuple(chain)
                    if key not in seen_chains:
                        seen_chains.add(key)
                        chains.append(chain)
            else:
                chain = [fault_name, cause_name]
                key = tuple(chain)
                if key not in seen_chains:
                    seen_chains.add(key)
                    chains.append(chain)

            # 多跳：递归查找子原因（深度2-3跳）
            _multi_hop_causes(
                fault_name, cause_entity, id2name, by_src,
                chains, seen_chains, max_chains, hop=2,
            )

            if len(chains) >= max_chains:
                break
        if len(chains) >= max_chains:
            break

    return chains[:max_chains]


def _multi_hop_causes(
    fault_name: str,
    cause_entity: KGEntity,
    id2name: dict,
    by_src: dict,
    chains: List[List[str]],
    seen_chains: set,
    max_chains: int,
    hop: int,
) -> None:
    """递归查找子原因，构建多跳推理链。"""
    if hop > MAX_HOP:
        return
    if len(chains) >= max_chains:
        return

    sub_causes = [
        r for r in by_src.get(cause_entity.id, [])
        if r.rel_type == "源于"
    ]

    for sc in sub_causes:
        sub_cause_entity = id2name.get(sc.dst_id)
        if not sub_cause_entity:
            continue
        sub_cause_name = sub_cause_entity.name

        # 构建 fault → cause → sub_cause 链路
        chain = [fault_name, cause_entity.name, sub_cause_name]
        key = tuple(chain)
        if key not in seen_chains:
            seen_chains.add(key)
            chains.append(chain)

        # 查找 sub_cause 对应的措施
        sub_measures = [
            r for r in by_src.get(sub_cause_entity.id, [])
            if r.rel_type == "采取"
        ]
        for sm in sub_measures:
            m_entity = id2name.get(sm.dst_id)
            if m_entity:
                chain = [fault_name, cause_entity.name, sub_cause_name, m_entity.name]
                key = tuple(chain)
                if key not in seen_chains:
                    seen_chains.add(key)
                    chains.append(chain)

        # 递归下一跳
        _multi_hop_causes(
            fault_name, sub_cause_entity, id2name, by_src,
            chains, seen_chains, max_chains, hop + 1,
        )

        if len(chains) >= max_chains:
            return


# =========================================================================
# 故障树分析（FTA）自动构建
# =========================================================================

def fault_tree(
    db: Session,
    query: str,
    contexts: Optional[List[dict]] = None,
    max_depth: int = 3,
) -> Optional[dict]:
    """从故障实体出发，自动构建故障树（FTA）结构。

    返回嵌套字典：
    {
        "name": "发动机过热",
        "type": "fault",
        "confidence": 1.0,
        "children": [
            {
                "name": "散热片堵塞",
                "type": "cause",
                "confidence": 0.85,
                "children": [
                    {
                        "name": "长期未保养",
                        "type": "cause",
                        "confidence": 0.72,
                        "children": [],
                        "measures": ["清理散热片", "定期保养"]
                    }
                ],
                "measures": ["清理散热片"]
            },
            ...
        ],
        "measures": ["清理散热片", "补充机油"]
    }

    可信度传播：每跳衰减 HOP_DECAY（0.85），越深层原因可信度越低。
    """
    haystack = query or ""
    if contexts:
        haystack += " " + " ".join(c.get("content", "") for c in contexts)
    if not haystack.strip():
        return None

    entities = db.execute(select(KGEntity)).scalars().all()
    id2name = {e.id: e for e in entities}

    # 找命中的故障实体
    hit_faults = [
        e for e in entities
        if e.etype == "fault" and len(e.name) >= 2 and e.name in haystack
    ]
    if not hit_faults:
        hit_faults = [
            e for e in entities
            if len(e.name) >= 2 and e.name in haystack
        ]
    if not hit_faults:
        return None

    all_rels = db.execute(select(KGRelation)).scalars().all()
    by_src: dict[int, list] = {}
    for r in all_rels:
        by_src.setdefault(r.src_id, []).append(r)

    # 取第一个命中故障构建树
    fault = hit_faults[0]

    def _build_node(entity: KGEntity, node_type: str, depth: int,
                    visited: Set[int]) -> dict:
        """递归构建故障树节点。"""
        confidence = HOP_DECAY ** (depth - 1) if depth > 1 else 1.0

        # 查找当前节点的措施
        measures = []
        measure_rels = [
            r for r in by_src.get(entity.id, [])
            if r.rel_type == "采取"
        ]
        for mr in measure_rels:
            m_entity = id2name.get(mr.dst_id)
            if m_entity:
                measures.append(m_entity.name)

        # 查找子原因
        children = []
        if depth < max_depth and entity.id not in visited:
            visited.add(entity.id)
            cause_rels = [
                r for r in by_src.get(entity.id, [])
                if r.rel_type == "源于"
            ]
            for cr in cause_rels:
                child_entity = id2name.get(cr.dst_id)
                if child_entity and child_entity.id not in visited:
                    child_node = _build_node(
                        child_entity, "cause", depth + 1, visited,
                    )
                    children.append(child_node)
            visited.discard(entity.id)

        return {
            "name": entity.name,
            "type": node_type,
            "confidence": round(confidence, 3),
            "measures": measures,
            "children": children,
        }

    tree = _build_node(fault, "fault", 1, set())

    # 根节点补充所有措施
    root_measures = []
    measure_rels = [
        r for r in by_src.get(fault.id, [])
        if r.rel_type == "采取"
    ]
    for mr in measure_rels:
        m_entity = id2name.get(mr.dst_id)
        if m_entity:
            root_measures.append(m_entity.name)
    tree["measures"] = root_measures

    # 统计
    def _count_nodes(node: dict) -> dict:
        total = 1
        causes = 1 if node["type"] in ("fault", "cause") else 0
        measures = len(node.get("measures", []))
        for child in node.get("children", []):
            sub = _count_nodes(child)
            total += sub["total"]
            causes += sub["causes"]
            measures += sub["measures"]
        return {"total": total, "causes": causes, "measures": measures}

    stats = _count_nodes(tree)

    return {
        "query": query,
        "tree": tree,
        "stats": {
            "total_nodes": stats["total"],
            "cause_nodes": stats["causes"],
            "measure_count": stats["measures"],
            "max_depth": max_depth,
        },
    }


# =========================================================================
# 多跳推理链带可信度（供 Agent 调用）
# =========================================================================

def reasoning_chain_with_confidence(
    db: Session,
    query: str,
    contexts: Optional[List[dict]] = None,
    max_chains: int = 6,
) -> List[dict]:
    """返回带可信度的推理链列表。

    每条链：{chain: [fault, cause, ...], confidence: 0.xx, hops: N}
    """
    chains = reasoning_chain(db, query, contexts, max_chains)
    result = []
    for chain in chains:
        hops = len(chain) - 1  # fault 到最后节点的跳数
        confidence = HOP_DECAY ** hops
        result.append({
            "chain": chain,
            "confidence": round(confidence, 3),
            "hops": hops,
        })
    return result
