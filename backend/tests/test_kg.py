"""知识图谱模块测试。"""

import app.kg_store as kg_store
from app.models import KGEntityAlias, KGRelation, KGRelationEvidence, RepairCase


def test_kg_graph(client, worker_headers):
    """知识图谱数据（节点 + 关系 + 统计）。"""
    resp = client.get("/api/kg/graph", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data
    assert "stats" in data
    # 种子数据有实体和关系
    assert len(data["nodes"]) > 0
    assert len(data["links"]) > 0
    # 节点结构校验
    node = data["nodes"][0]
    assert "id" in node
    assert "name" in node
    assert "etype" in node
    assert "degree" in node


def test_reasoning_chain(client, worker_headers):
    """推理链接口：从故障实体推理出 故障→原因→措施 链路。"""
    resp = client.get(
        "/api/kg/reasoning",
        params={"query": "怠速不稳"},
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "怠速不稳"
    assert isinstance(data["chains"], list)
    assert "total" in data
    # 种子数据中"怠速不稳"有完整的 故障→原因→措施 链路
    assert data["total"] > 0
    # 每条链路至少包含故障与原因
    for chain in data["chains"]:
        assert len(chain) >= 2


def test_entity_cases(client, worker_headers):
    """实体溯源：返回该实体相关的案例与相邻实体。"""
    # 先获取图谱，找一个有连接的实体
    resp = client.get("/api/kg/graph", headers=worker_headers)
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert len(nodes) > 0

    # 优先选 degree > 0 的节点（有连接关系，更可能有案例）
    target = next((n for n in nodes if n["degree"] > 0), nodes[0])
    eid = target["id"]

    # 查询该实体的案例与邻居
    resp = client.get(f"/api/kg/entities/{eid}/cases", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "entity" in data
    assert data["entity"]["id"] == eid
    assert isinstance(data["cases"], list)
    assert isinstance(data["neighbors"], list)


def test_relation_provenance_endpoint(client, worker_headers, db_session):
    relation = db_session.query(KGRelation).first()
    response = client.get(
        f"/api/kg/relations/{relation.id}/evidence",
        headers=worker_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["relation"]["id"] == relation.id
    assert data["evidence"]
    assert data["evidence"][0]["review_status"] == "approved"
    assert 0 <= data["evidence"][0]["confidence"] <= 1


def test_entity_alignment_records_alias(db_session, monkeypatch):
    case = db_session.query(RepairCase).filter(RepairCase.status == "approved").first()
    canonical = "国特测试一号泵"
    alias = "国特测试1#泵"
    monkeypatch.setattr(
        kg_store,
        "align_extraction",
        lambda db, entities: {alias: canonical, "测试振动": "测试振动"},
    )
    try:
        kg_store.persist_extraction(db_session, case.id, {
            "entities": [
                {"name": alias, "etype": "device"},
                {"name": "测试振动", "etype": "fault"},
            ],
            "relations": [{
                "source": alias,
                "rel": "发生",
                "target": "测试振动",
                "evidence": "现场记录显示一号泵出现测试振动。",
                "confidence": 0.82,
            }],
        })
        stored_alias = db_session.query(KGEntityAlias).filter(
            KGEntityAlias.alias == alias,
        ).one()
        evidence = db_session.query(KGRelationEvidence).filter(
            KGRelationEvidence.evidence_text.contains("一号泵"),
        ).one()
        assert stored_alias.normalization_method == "entity_alignment"
        assert evidence.confidence == 0.82
        assert evidence.extraction_method == "llm_aligned"
    finally:
        db_session.rollback()
