"""文档导入：PDF -> 按页提取文本 -> 切块 -> 向量化 -> 入库。

用于把检修手册（如摩托车发动机维修手册）沉淀为可检索知识。
无需 VL Key，纯文本链路。
"""
from typing import List, Tuple

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from .embedding import get_embedder
from .models import DocChunk, Document

# 切块参数：按字符近似切分，带重叠以减少语义割裂
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


def _split_text(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - CHUNK_OVERLAP
    return chunks


def extract_pdf_chunks(pdf_path: str) -> List[Tuple[int, str]]:
    """返回 [(page, chunk_text), ...]，page 从 1 开始。"""
    out: List[Tuple[int, str]] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text("text")
            for chunk in _split_text(text):
                out.append((page_index + 1, chunk))
    finally:
        doc.close()
    return out


def ingest_pdf(
    db: Session,
    pdf_path: str,
    title: str,
    device_type: str = "",
    device_model: str = "",
    source_type: str = "manual",
    status: str = "approved",
) -> Document:
    """解析 PDF 并写入 documents + doc_chunks（含向量）。返回 Document。"""
    page_chunks = extract_pdf_chunks(pdf_path)
    if not page_chunks:
        raise ValueError("PDF 未提取到文本（可能是扫描件，需 OCR）")

    doc = Document(
        title=title, source_type=source_type, device_type=device_type,
        device_model=device_model, file_path=pdf_path, status=status,
    )
    db.add(doc)
    db.flush()

    texts = [c[1] for c in page_chunks]
    embedder = get_embedder()
    # 分批嵌入，避免单次过大
    batch = 32
    vectors: List[List[float]] = []
    for i in range(0, len(texts), batch):
        vectors.extend(embedder.embed(texts[i:i + batch]))

    for (page, content), vec in zip(page_chunks, vectors):
        db.add(DocChunk(doc_id=doc.id, content=content, page=page, embedding=vec))
    db.commit()
    db.refresh(doc)
    return doc


if __name__ == "__main__":
    # 命令行导入：python -m app.ingest <pdf路径> <标题> [设备类型] [设备型号]
    import sys

    from .db import SessionLocal

    if len(sys.argv) < 3:
        print("用法: python -m app.ingest <pdf路径> <标题> [设备类型] [设备型号]")
        raise SystemExit(1)
    pdf_path, title = sys.argv[1], sys.argv[2]
    device_type = sys.argv[3] if len(sys.argv) > 3 else ""
    device_model = sys.argv[4] if len(sys.argv) > 4 else ""
    _db = SessionLocal()
    try:
        d = ingest_pdf(_db, pdf_path, title, device_type, device_model)
        cnt = len(d.chunks)
        print(f"导入完成：《{d.title}》 doc_id={d.id}，共 {cnt} 个分块。")
    finally:
        _db.close()
