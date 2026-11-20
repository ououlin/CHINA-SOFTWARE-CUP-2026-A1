"""问答模块测试。"""

import app.routers.chat as chat_router
from app.models import Device


def test_health(client):
    """健康检查端点。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_ask_endpoint(client, worker_headers):
    """文本问答接口（mock LLM 返回固定文本）。"""
    resp = client.post(
        "/api/chat/ask",
        json={"query": "发动机怠速不稳怎么排查？"},
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert data["qa_id"] is not None
    assert isinstance(data["citations"], list)
    # 置信度信息应存在
    assert "confidence" in data


def test_ask_with_history(client, worker_headers):
    """多轮对话：带上历史记录追问。"""
    resp = client.post(
        "/api/chat/ask",
        json={
            "query": "那气门间隙标准值是多少？",
            "history": [
                {"role": "user", "content": "发动机怠速不稳怎么排查？"},
                {"role": "assistant", "content": "建议检查火花塞与气门间隙。"},
            ],
        },
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["answer"]) > 0
    assert data["qa_id"] is not None


def test_ask_with_device_model(client, worker_headers):
    """带设备型号过滤的问答，引用片段应全部来自指定型号。"""
    resp = client.post(
        "/api/chat/ask",
        json={
            "query": "火花塞怎么检查？",
            "device_model": "通用四冲程",
        },
        headers=worker_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["answer"]) > 0
    # 若有引用片段，则其设备型号应与过滤条件一致
    for cite in data["citations"]:
        assert cite["device_model"] == "通用四冲程"


def test_ask_stream_reports_generator_failure_and_still_finishes(
    client, worker_headers, monkeypatch,
):
    """模型流中断须显式发 error，并继续落库发 done，避免前端永久等待。"""
    def broken_generator():
        yield "已生成部分"
        raise RuntimeError("injected stream failure")

    monkeypatch.setattr(chat_router, "answer_stream", lambda *_args, **_kwargs: (
        [], [], None, [], [], None,
        {"level": "low", "requires_human_confirmation": False,
         "categories": [], "message": ""},
        broken_generator,
    ))
    response = client.post(
        "/api/chat/ask_stream",
        json={"query": "故障注入测试"},
        headers=worker_headers,
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "injected stream failure" in response.text
    assert "event: done" in response.text


def test_diagnose_stream_error_still_emits_terminal_done(
    client, worker_headers, monkeypatch,
):
    monkeypatch.setattr(chat_router, "react_diagnose_stream", lambda *_args, **_kwargs: iter([
        {"phase": "error", "message": "injected agent failure"},
    ]))
    response = client.post(
        "/api/chat/diagnose_stream",
        json={"query": "Agent故障注入测试"},
        headers=worker_headers,
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "event: done" in response.text
    assert '"status": "incomplete"' in response.text


def test_image_ask_injects_selected_device_context(
    client, worker_headers, db_session, monkeypatch,
):
    """图片问答选择设备后，应使用该设备型号并注入维修档案。"""
    device = db_session.query(Device).first()
    captured = {}

    monkeypatch.setattr(chat_router, "analyze_image", lambda *_args, **_kwargs: {
        "is_industrial_fault": True,
        "confidence": 0.95,
        "description": "设备部件存在异常磨损",
    })

    def fake_answer_image_stream(
        db, image_desc, user_text=None, device_model=None, device_context="",
    ):
        captured["device_model"] = device_model
        captured["device_context"] = device_context
        return [], lambda: iter(["测试回答"])

    monkeypatch.setattr(chat_router, "answer_image_stream", fake_answer_image_stream)
    resp = client.post(
        "/api/chat/ask_image",
        data={"query": "请诊断", "device_id": str(device.id)},
        files={"image": ("fault.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        headers=worker_headers,
    )
    assert resp.status_code == 200
    assert captured["device_model"] == device.device_model
    assert device.name in captured["device_context"]
