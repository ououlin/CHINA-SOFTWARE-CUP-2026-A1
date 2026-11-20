"""问答路由：文本问答（一次性 + 流式）+ 多模态图片问答（流式）。"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import SessionLocal, get_db
from ..models import QALog, User
from ..ratelimit import rate_limit
from ..rag.confidence import score_confidence
from ..rag.device_context import device_context_text, get_device
from ..rag.pipeline import answer, answer_stream
from ..rag.multimodal import (
    analyze_image, guard_image, answer_image_stream, ImageRejected,
)
from ..rag.security import assess_operational_risk
from ..rag.agent_diagnosis import diagnose as agent_diagnose
from ..rag.agent_diagnosis import react_diagnose_stream
from ..schemas import AskReq, AskResp, DiagnoseReq, DiagnoseResp
from ..upload_guard import ensure_image, read_upload_limited

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ask", response_model=AskResp)
def ask(req: AskReq, db: Session = Depends(get_db),
        user: User = Depends(rate_limit("chat", "rate_limit_chat"))):
    result = answer(db, req.query, device_model=req.device_model,
                    history=[h.model_dump() for h in req.history], user_id=user.id,
                    device_id=req.device_id)
    log = QALog(user_id=user.id, query=req.query, modality="text",
                answer=result["answer"], citations=result["citations"])
    db.add(log)
    db.commit()
    db.refresh(log)
    return {**result, "qa_id": log.id}


@router.post("/ask_stream")
def ask_stream(req: AskReq, db: Session = Depends(get_db),
               user: User = Depends(rate_limit("chat", "rate_limit_chat"))):
    """SSE 流式：citations -> (corrections 若命中反馈增强) -> delta... -> done(含 qa_id)。"""
    contexts, corrections, rewritten, graph, sops, device, safety, gen = answer_stream(
        db, req.query, device_model=req.device_model,
        history=[h.model_dump() for h in req.history], user_id=user.id,
        device_id=req.device_id)

    def event_stream():
        # 注意：在 FastAPI 中，StreamingResponse 返回后依赖注入的 db 会话会被关闭，
        # 因此生成器内部必须创建独立的会话来完成 QALog 落库。
        stream_db = SessionLocal()
        try:
            if rewritten:
                yield f"event: rewrite\ndata: {json.dumps(rewritten, ensure_ascii=False)}\n\n"
            yield f"event: safety\ndata: {json.dumps(safety, ensure_ascii=False)}\n\n"
            yield f"event: citations\ndata: {json.dumps(contexts, ensure_ascii=False)}\n\n"
            if graph:
                yield f"event: graph\ndata: {json.dumps(graph, ensure_ascii=False)}\n\n"
            if sops:
                yield f"event: sops\ndata: {json.dumps(sops, ensure_ascii=False)}\n\n"
            if corrections:
                yield f"event: corrections\ndata: {json.dumps(corrections, ensure_ascii=False)}\n\n"
            buffer = []
            try:
                for piece in gen():
                    buffer.append(piece)
                    yield f"event: delta\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"
            except Exception as e:
                # 云端 API 中途断开/超时：发 error 事件，避免前端流式卡死；已生成部分仍落库
                yield f"event: error\ndata: {json.dumps(f'生成中断：{e}', ensure_ascii=False)}\n\n"
            full = "".join(buffer)
            confidence = score_confidence(contexts, corrections, graph, full, device=device)
            yield f"event: confidence\ndata: {json.dumps(confidence, ensure_ascii=False)}\n\n"
            log = QALog(user_id=user.id, query=req.query, modality="text",
                        answer=full, citations=contexts)
            stream_db.add(log)
            stream_db.commit()
            stream_db.refresh(log)
            yield f"event: done\ndata: {json.dumps({'qa_id': log.id})}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


@router.post("/ask_image")
async def ask_image(
    image: UploadFile = File(...),
    query: Optional[str] = Form(None),
    device_model: Optional[str] = Form(None),
    device_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(rate_limit("upload", "rate_limit_upload")),
):
    """多模态：上传故障图片(+可选文字/型号) -> Qwen-VL 看图 -> 检索 -> 诊断。

    SSE 事件：vl(图片识别描述) -> citations -> delta... -> done。
    """
    mime = image.content_type or ""
    if mime not in _ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail=f"不支持的图片类型：{mime or 'unknown'}")
    image_bytes = await read_upload_limited(image, settings.max_image_upload_mb)
    mime = ensure_image(image_bytes, mime, _ALLOWED_IMAGE)

    try:
        analysis = analyze_image(image_bytes, mime=mime)
    except RuntimeError as e:
        # 多为未配置 DASHSCOPE_API_KEY
        raise HTTPException(status_code=503, detail=str(e))

    # 双重校验：非设备故障图 / 置信度过低 -> 422 拦截，不进入检索与生成
    try:
        guard_image(analysis)
    except ImageRejected as e:
        raise HTTPException(
            status_code=422,
            detail={"reject": True, "message": str(e), "confidence": e.confidence},
        )

    image_desc = analysis["description"]
    device = get_device(db, device_id)
    effective_model = device.device_model if device else device_model
    contexts, gen = answer_image_stream(
        db, image_desc, user_text=query, device_model=effective_model,
        device_context=device_context_text(db, device),
    )
    safety = assess_operational_risk(f"{query or ''}\n{image_desc}")

    def event_stream():
        # 创建独立的数据库会话，避免 StreamingResponse 返回后依赖注入的会话被关闭
        stream_db = SessionLocal()
        try:
            yield f"event: vl\ndata: {json.dumps(image_desc, ensure_ascii=False)}\n\n"
            yield f"event: safety\ndata: {json.dumps(safety, ensure_ascii=False)}\n\n"
            yield f"event: citations\ndata: {json.dumps(contexts, ensure_ascii=False)}\n\n"
            buffer = []
            try:
                for piece in gen():
                    buffer.append(piece)
                    yield f"event: delta\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps(f'生成中断：{e}', ensure_ascii=False)}\n\n"
            full = "".join(buffer)
            confidence = score_confidence(contexts, [], [], full)
            yield f"event: confidence\ndata: {json.dumps(confidence, ensure_ascii=False)}\n\n"
            q_text = query or "[图片故障诊断]"
            log = QALog(user_id=user.id, query=q_text, modality="image",
                        answer=full, citations=contexts)
            stream_db.add(log)
            stream_db.commit()
            stream_db.refresh(log)
            yield f"event: done\ndata: {json.dumps({'qa_id': log.id})}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/diagnose")
def diagnose(req: DiagnoseReq, db: Session = Depends(get_db),
             user: User = Depends(rate_limit("chat", "rate_limit_chat"))):
    """Agent 自主诊断（G9）：问题分解→多路检索→交叉验证→诊断报告。

    与普通问答的区别：普通问答是单次检索→生成，
    诊断引擎模拟专家思路，多步推理、交叉验证，输出结构化诊断报告。
    """
    result = agent_diagnose(
        db, req.query, device_model=req.device_model,
        device_id=req.device_id,
    )
    result["safety"] = assess_operational_risk(f"{req.query}\n{result['report']}")
    # 落库
    log = QALog(
        user_id=user.id, query=req.query, modality="text",
        answer=result["report"], citations=result["all_citations"],
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {**result, "qa_id": log.id}


@router.post("/diagnose_stream")
def diagnose_stream(req: DiagnoseReq, db: Session = Depends(get_db),
                    user: User = Depends(rate_limit("chat", "rate_limit_chat"))):
    """Agent 自主诊断（G9 · ReAct 流式版）：SSE 逐步推送推理过程。

    SSE 事件：
      - thought: 每轮推理的 Thought
      - action: 工具调用（含工具名、参数、观察结果）
      - report: 最终诊断报告
      - confidence: 置信度评估
      - done: 完成信号（含 qa_id）
    """
    def event_stream():
        stream_db = SessionLocal()
        try:
            safety = assess_operational_risk(req.query)
            yield f"event: safety\ndata: {json.dumps(safety, ensure_ascii=False)}\n\n"
            full_report = ""
            all_citations = []
            completed = False
            stream_error = ""
            for step in react_diagnose_stream(
                stream_db, req.query,
                device_model=req.device_model,
                device_id=req.device_id,
            ):
                phase = step.get("phase", "")
                if phase == "thought":
                    yield f"event: thought\ndata: {json.dumps(step, ensure_ascii=False)}\n\n"
                elif phase == "action":
                    if step.get("citations"):
                        all_citations.extend(step["citations"])
                    yield f"event: action\ndata: {json.dumps(step, ensure_ascii=False)}\n\n"
                elif phase == "report":
                    full_report = step.get("report", "")
                    yield f"event: report\ndata: {json.dumps(step, ensure_ascii=False)}\n\n"
                elif phase == "confidence":
                    yield f"event: confidence\ndata: {json.dumps(step.get('confidence', {}), ensure_ascii=False)}\n\n"
                elif phase == "error":
                    stream_error = step.get("message", "")
                    yield f"event: error\ndata: {json.dumps(stream_error, ensure_ascii=False)}\n\n"
                elif phase == "done":
                    log = QALog(
                        user_id=user.id, query=req.query, modality="text",
                        answer=full_report, citations=all_citations,
                    )
                    stream_db.add(log)
                    stream_db.commit()
                    stream_db.refresh(log)
                    completed = True
                    yield f"event: done\ndata: {json.dumps({'qa_id': log.id, **step}, ensure_ascii=False)}\n\n"
            if not completed:
                # 统一 SSE 终止契约：即使 Agent 失败也发 done，客户端不会永久等待。
                log = QALog(
                    user_id=user.id, query=req.query, modality="text",
                    answer=full_report, citations=all_citations,
                )
                stream_db.add(log)
                stream_db.commit()
                stream_db.refresh(log)
                payload = {
                    "qa_id": log.id,
                    "status": "incomplete",
                    "error": stream_error or "Agent stream ended unexpectedly",
                }
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
