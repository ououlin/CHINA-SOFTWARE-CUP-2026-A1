"""文档路由：列表查询 + PDF 手册导入（解析→切块→向量化→入库）。"""
import os
import uuid
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..db import get_db
from ..ingest import ingest_pdf
from ..models import Document, User
from ..schemas import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("", response_model=List[DocumentOut])
def list_documents(db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    rows = db.execute(select(Document).order_by(Document.id.desc())).scalars().all()
    return rows


@router.post("/upload", response_model=DocumentOut)
async def upload_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    device_type: str = Form(""),
    device_model: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("auditor", "admin")),
):
    """上传 PDF 检修手册并入库（仅审核员/管理员）。"""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}.pdf")
    with open(save_path, "wb") as f:
        f.write(await file.read())

    try:
        doc = ingest_pdf(
            db, save_path,
            title=title or os.path.splitext(file.filename)[0],
            device_type=device_type, device_model=device_model,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        # 例如部署环境未安装 PyMuPDF：给出明确提示而非 500
        raise HTTPException(status_code=503, detail=str(e))
    return doc
