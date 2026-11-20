"""上传文件安全校验：大小限制、MIME 白名单与文件头校验。"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile


async def read_upload_limited(file: UploadFile, max_mb: int) -> bytes:
    max_bytes = max_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"文件超过大小限制（最大 {max_mb}MB）")
    return data


def ensure_pdf(data: bytes, filename: str = "") -> None:
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if filename and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="文件内容不是有效 PDF")


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def ensure_image(data: bytes, mime: str, allowed: set[str]) -> str:
    if not data:
        raise HTTPException(status_code=400, detail="图片为空")
    detected = image_kind(data)
    if detected is None:
        raise HTTPException(status_code=400, detail="文件内容不是有效图片")
    if detected not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的图片类型：{detected}")
    if mime and mime in allowed and mime != detected:
        raise HTTPException(status_code=400, detail="图片 MIME 与文件内容不一致")
    return detected
