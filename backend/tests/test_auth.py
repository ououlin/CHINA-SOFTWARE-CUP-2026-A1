"""认证模块测试。"""


def test_login_success(client):
    """正确用户名密码登录。"""
    resp = client.post(
        "/api/auth/login",
        data={"username": "worker", "password": "worker123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "worker"
    assert data["role"] == "worker"


def test_login_wrong_password(client):
    """错误密码登录应返回 400。"""
    resp = client.post(
        "/api/auth/login",
        data={"username": "worker", "password": "wrong_password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400
    assert "错误" in resp.json()["detail"]


def test_login_nonexistent(client):
    """不存在的用户登录应返回 400。"""
    resp = client.post(
        "/api/auth/login",
        data={"username": "ghost_user", "password": "whatever"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400
    assert "错误" in resp.json()["detail"]


def test_me_with_token(client, worker_headers):
    """带 token 获取当前用户信息。"""
    resp = client.get("/api/auth/me", headers=worker_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "worker"
    assert data["role"] == "worker"
    assert "id" in data


def test_me_without_token(client):
    """无 token 访问 /me 应返回 401。"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_role_based_access(client, worker_headers, admin_headers):
    """角色权限控制：worker 不能建设备（403），admin 可以（200）。"""
    # worker 无权建档（仅 auditor/admin 可操作）
    resp = client.post(
        "/api/devices",
        json={
            "code": "TEST-ROLE-001",
            "name": "权限测试设备",
            "device_type": "测试类型",
            "device_model": "测试型号",
        },
        headers=worker_headers,
    )
    assert resp.status_code == 403

    # admin 可以建档
    resp = client.post(
        "/api/devices",
        json={
            "code": "TEST-ROLE-002",
            "name": "权限测试设备2",
            "device_type": "测试类型",
            "device_model": "测试型号",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "TEST-ROLE-002"
