"""问答路由：文本问答（一次性 + 流式）+ 多模态图片问答（流式）。"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import QALog, User
from ..rag.pipeline import answer, answer_stream
from ..rag.multimodal import answer_image_stream
from ..schemas import AskReq, AskResp

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ask", response_model=AskResp)
def ask(req: AskReq, db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    result = answer(db, req.query, device_model=req.device_model)
    db.add(QALog(user_id=user.id, query=req.query, modality="text",
                 answer=result["answer"], citations=result["citations"]))
    db.commit()
    return result


@router.post("/ask_stream")
def ask_stream(req: AskReq, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """SSE 流式返回。先推送一条 citations 事件，再推送增量 token，最后 done。"""
    contexts, gen = answer_stream(db, req.query, device_model=req.device_model)

    def event_stream():
        yield f"event: citations\ndata: {json.dumps(contexts, ensure_ascii=False)}\n\n"
        buffer = []
        for piece in gen():
            buffer.append(piece)
            yield f"event: delta\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"
        full = "".join(buffer)
        db.add(QALog(user_id=user.id, query=req.query, modality="text",
                     answer=full, citations=contexts))
        db.commit()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


@router.post("/ask_image")
async def ask_image(
    image: UploadFile = File(...),
    query: Optional[str] = Form(None),
    device_model: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
        for piece in gen():
            buffer.append(piece)
            yield f"event: delta\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"
        full = "".join(buffer)
        q_text = query or "[图片故障诊断]"
        db.add(QALog(user_id=user.id, query=q_text, modality="image",
                     answer=full, citations=contexts))
        db.commit()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
