"""问答路由：文本问答（一次性 + 流式）+ 多模态图片问答（流式）。"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import QALog, User
from ..ratelimit import rate_limit
from ..rag.pipeline import answer, answer_stream
from ..rag.multimodal import answer_image_stream
from ..schemas import AskReq, AskResp

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ask", response_model=AskResp)
def ask(req: AskReq, db: Session = Depends(get_db),
        user: User = Depends(rate_limit("chat", "rate_limit_chat"))):
    result = answer(db, req.query, device_model=req.device_model,
                    history=[h.model_dump() for h in req.history])
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
    contexts, corrections, rewritten, graph, gen = answer_stream(
        db, req.query, device_model=req.device_model,
        history=[h.model_dump() for h in req.history])

    def event_stream():
        if rewritten:
            yield f"event: rewrite\ndata: {json.dumps(rewritten, ensure_ascii=False)}\n\n"
        yield f"event: citations\ndata: {json.dumps(contexts, ensure_ascii=False)}\n\n"
        if graph:
            yield f"event: graph\ndata: {json.dumps(graph, ensure_ascii=False)}\n\n"
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
        log = QALog(user_id=user.id, query=req.query, modality="text",
                    answer=full, citations=contexts)
        db.add(log)
        db.commit()
        db.refresh(log)
        yield f"event: done\ndata: {json.dumps({'qa_id': log.id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


@router.post("/ask_image")
async def ask_image(
    image: UploadFile = File(...),
    query: Optional[str] = Form(None),
    device_model: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(rate_limit("upload", "rate_limit_upload")),
):
    """多模态：上传故障图片(+可选文字/型号) -> Qwen-VL 看图 -> 检索 -> 诊断。

    SSE 事件：vl(图片识别描述) -> citations -> delta... -> done。
    """
    mime = image.content_type or "image/jpeg"
    if mime not in _ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail=f"不支持的图片类型：{mime}")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="图片为空")

    try:
        image_desc, contexts, gen = answer_image_stream(
            db, image_bytes, user_text=query, device_model=device_model, mime=mime,
        )
    except RuntimeError as e:
        # 多为未配置 DASHSCOPE_API_KEY
        raise HTTPException(status_code=503, detail=str(e))

    def event_stream():
        yield f"event: vl\ndata: {json.dumps(image_desc, ensure_ascii=False)}\n\n"
        yield f"event: citations\ndata: {json.dumps(contexts, ensure_ascii=False)}\n\n"
        buffer = []
        try:
            for piece in gen():
                buffer.append(piece)
                yield f"event: delta\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps(f'生成中断：{e}', ensure_ascii=False)}\n\n"
        full = "".join(buffer)
        q_text = query or "[图片故障诊断]"
        log = QALog(user_id=user.id, query=q_text, modality="image",
                    answer=full, citations=contexts)
        db.add(log)
        db.commit()
        db.refresh(log)
        yield f"event: done\ndata: {json.dumps({'qa_id': log.id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
