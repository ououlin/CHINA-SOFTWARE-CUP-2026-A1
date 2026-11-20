"""反馈/标注模块测试。"""

from app.models import QALog


def test_create_feedback(client, worker_headers, db_session):
    """创建反馈（点赞）。"""
    # 取一条已存在的问答记录作为反馈对象
    qa = db_session.query(QALog).first()
    assert qa is not None, "种子数据应包含问答记录"

    resp = client.post(
        "/api/feedback",
        json={"qa_id": qa.id, "vote": "up"},
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["qa_id"] == qa.id
    assert data["vote"] == "up"
    assert data["status"] == "active"


def test_feedback_stats(client, worker_headers):
    """反馈统计：返回点赞、点踩、修正数量。"""
    resp = client.get("/api/feedback/stats", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "up" in data
    assert "down" in data
    assert "corrections" in data
    assert "pending" in data
    # 值应为非负整数
    assert isinstance(data["up"], int)
    assert isinstance(data["down"], int)
    assert data["up"] >= 0
    assert data["down"] >= 0
