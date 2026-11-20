"""设备健康档案模块测试。"""


def test_list_devices(client, worker_headers):
    """设备台账列表。"""
    resp = client.get("/api/devices", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0  # 种子数据有设备
    # 验证字段结构
    first = data[0]
    assert "id" in first
    assert "code" in first
    assert "name" in first
    assert "status" in first


def test_create_device(client, admin_headers):
    """管理员创建设备。"""
    resp = client.post(
        "/api/devices",
        json={
            "code": "TEST-DEV-001",
            "name": "测试用发动机",
            "device_type": "摩托车发动机",
            "device_model": "通用四冲程",
            "location": "测试位置",
            "status": "normal",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "TEST-DEV-001"
    assert data["name"] == "测试用发动机"
    assert data["device_type"] == "摩托车发动机"


def test_device_detail(client, worker_headers, admin_headers):
    """设备详情含检修记录字段。"""
    # 先创建一台设备
    create = client.post(
        "/api/devices",
        json={
            "code": "TEST-DEV-DETAIL-001",
            "name": "详情测试设备",
            "device_type": "摩托车发动机",
            "device_model": "通用四冲程",
            "location": "测试位置",
        },
        headers=admin_headers,
    )
    assert create.status_code == 200
    did = create.json()["id"]

    # 查询详情
    resp = client.get(f"/api/devices/{did}", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == did
    assert "records" in data
    assert isinstance(data["records"], list)
    assert "linked_cases" in data
    assert "linked_sops" in data


def test_create_maintenance_record(client, worker_headers, admin_headers):
    """提交报修记录。"""
    # 先建设备
    create = client.post(
        "/api/devices",
        json={
            "code": "TEST-DEV-REPAIR-001",
            "name": "报修测试设备",
            "device_type": "摩托车发动机",
            "device_model": "通用四冲程",
        },
        headers=admin_headers,
    )
    assert create.status_code == 200
    did = create.json()["id"]

    # 提交报修
    resp = client.post(
        f"/api/devices/{did}/records",
        json={
            "title": "测试报修：怠速不稳",
            "fault_desc": "冷车怠速抖动明显",
            "severity": "general",
        },
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "测试报修：怠速不稳"
    assert data["status"] == "open"
    assert data["device_id"] == did
