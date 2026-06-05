"""Pydantic 请求/响应模型。"""
from datetime import datetime
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


# ---- M3 标准化作业指引（SOP）----
class StepIn(BaseModel):
    order_no: int = 1
    title: str
    instruction: str = ""
    risk: str = ""
    tools: str = ""
    is_required: bool = False
    checkpoint: str = ""


class StepOut(StepIn):
    id: int

    class Config:
        from_attributes = True


class SOPTemplateIn(BaseModel):
    name: str
    device_type: str = ""
    device_model: str = ""
    repair_level: str = ""
    summary: str = ""
    steps: List[StepIn] = []


class SOPTemplateBrief(BaseModel):
    id: int
    name: str
    device_type: str
    device_model: str
    repair_level: str
    summary: str
    source: str
    status: str
    step_count: int = 0


class SOPTemplateOut(SOPTemplateBrief):
    steps: List[StepOut] = []


class SOPGenerateReq(BaseModel):
    device_type: str
    device_model: Optional[str] = None
    repair_level: str = "二级维护"


class SOPRunSubmit(BaseModel):
    template_id: int
    device_model: Optional[str] = None
    checked_step_ids: List[int] = []
    note: str = ""


class SOPRunOut(BaseModel):
    id: int
    template_id: int
    template_name: str = ""
    device_model: str
    status: str
    note: str
    created_at: datetime

    class Config:
        from_attributes = True
