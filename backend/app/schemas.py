"""Pydantic 请求/响应模型。"""
from typing import List, Optional

from pydantic import BaseModel


# ---- 鉴权 ----
class LoginResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    display_name: str
    role: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str

    class Config:
        from_attributes = True


# ---- 问答 ----
class AskReq(BaseModel):
    query: str
    device_model: Optional[str] = None


class Citation(BaseModel):
    chunk_id: int
    doc_id: int
    doc_title: str
    device_model: str
    page: int
    content: str
    score: float


class AskResp(BaseModel):
    answer: str
    citations: List[Citation]


# ---- 文档 ----
class DocumentOut(BaseModel):
    id: int
    title: str
    source_type: str
    device_model: str
    device_type: str
    status: str

    class Config:
        from_attributes = True
