"""标准化作业指引（SOP）模块测试。"""


def test_list_sop_templates(client, worker_headers):
    """SOP 模板列表。"""
    resp = client.get("/api/sop/templates", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0  # 种子数据有 SOP
    # 一线人员仅见已发布模板
    for tpl in data:
        assert tpl["status"] == "approved"


def test_sop_detail(client, worker_headers):
    """SOP 详情含步骤。"""
    # 先获取模板列表
    resp = client.get("/api/sop/templates", headers=worker_headers)
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) > 0
    tid = templates[0]["id"]

    # 查询详情
    resp = client.get(f"/api/sop/templates/{tid}", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == tid
    assert "steps" in data
    assert len(data["steps"]) > 0
    # 验证步骤结构
    step = data["steps"][0]
    assert "order_no" in step
    assert "title" in step
    assert "is_required" in step


def test_sop_run(client, worker_headers):
    """执行 SOP（勾选所有步骤含合规必检项）。"""
    # 获取一个已发布模板
    resp = client.get("/api/sop/templates", headers=worker_headers)
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) > 0
    tid = templates[0]["id"]

    # 获取详情，找出所有步骤 ID
    resp = client.get(f"/api/sop/templates/{tid}", headers=worker_headers)
    assert resp.status_code == 200
    detail = resp.json()
    all_step_ids = [s["id"] for s in detail["steps"]]
    assert len(all_step_ids) > 0

    # 提交执行（勾选所有步骤，包含合规必检项）
    resp = client.post(
        "/api/sop/runs",
        json={
            "template_id": tid,
            "checked_step_ids": all_step_ids,
            "note": "测试执行 SOP",
        },
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["template_id"] == tid
    assert data["template_name"] != ""
