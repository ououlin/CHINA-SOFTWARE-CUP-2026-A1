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
class ChatTurn(BaseModel):
    role: str          # user / assistant
    content: str


class AskReq(BaseModel):
    query: str
    device_model: Optional[str] = None
    history: List[ChatTurn] = []   # 多轮上下文（不含本次 query），按时间正序


class Citation(BaseModel):
    chunk_id: int
    doc_id: int
    doc_title: str
    device_model: str
    page: int
    content: str
    score: float


class AppliedCorrection(BaseModel):
    """本次回答采纳的人工修正知识（反馈增强）。"""
    id: int
    query: str
    correction_text: str
    score: float


class AskResp(BaseModel):
    answer: str
    citations: List[Citation]
    qa_id: Optional[int] = None
    corrections: List[AppliedCorrection] = []


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


# ---- M4 知识沉淀（检修案例 + 知识图谱）----
class RepairCaseIn(BaseModel):
    title: str
    device_type: str = ""
    device_model: str = ""
    content: str


class RepairCaseBrief(BaseModel):
    id: int
    title: str
    device_type: str
    device_model: str
    status: str
    author_name: str = ""
    created_at: datetime


class RepairCaseOut(RepairCaseBrief):
    content: str
    review_note: str = ""
    doc_id: Optional[int] = None
    entity_count: int = 0      # 审核通过后抽取到的实体数
    relation_count: int = 0    # 抽取到的关系数


class CaseReviewReq(BaseModel):
    action: str                # approve 采纳入库 / reject 退回
    note: str = ""


class KGNode(BaseModel):
    id: int
    name: str
    etype: str
    degree: int = 0            # 连接的关系数，前端用于节点大小


class KGLink(BaseModel):
    source: int
    target: int
    rel: str


class KGGraph(BaseModel):
    nodes: List[KGNode] = []
    links: List[KGLink] = []
    stats: dict = {}           # 各类型实体数量统计


class KGCaseBrief(BaseModel):
    id: int
    title: str
    device_model: str = ""
    status: str = ""


class KGEntityCases(BaseModel):
    entity: KGNode
    cases: List[KGCaseBrief] = []
    neighbors: List[KGNode] = []   # 直接相邻实体


# ---- M5 大模型输出标注与修正 ----
class FeedbackIn(BaseModel):
    qa_id: int
    # None=不变；vote: ""清除/up/down；correction_text: ""清除/文本设置（独立更新互不覆盖）
    vote: Optional[str] = None
    correction_text: Optional[str] = None


class FeedbackOut(BaseModel):
    id: int
    qa_id: Optional[int] = None
    vote: str
    correction_text: str
    query: str
    status: str
    user_name: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackStats(BaseModel):
    up: int = 0
    down: int = 0
    corrections: int = 0           # 生效中的纠正条数


# ---- 增强 G1 设备健康档案（一机一档）----
class DeviceIn(BaseModel):
    code: str
    name: str
    device_type: str = ""
    device_model: str = ""
    location: str = ""
    status: str = "normal"
    commissioned_at: Optional[datetime] = None
    note: str = ""


class DeviceBrief(BaseModel):
    id: int
    code: str
    name: str
    device_type: str
    device_model: str
    location: str
    status: str
    fault_count: int = 0           # 累计报修/故障次数
    open_count: int = 0            # 未结报修数
    created_at: datetime


class MaintenanceRecordIn(BaseModel):
    title: str
    fault_desc: str = ""
    severity: str = "general"


class MaintenanceRecordHandle(BaseModel):
    handling: str = ""
    status: str = "done"           # processing 处理中 / done 已完成


class MaintenanceRecordOut(BaseModel):
    id: int
    device_id: int
    title: str
    fault_desc: str
    handling: str
    severity: str
    status: str
    reporter_name: str = ""
    handler_name: str = ""
    created_at: datetime
    done_at: Optional[datetime] = None


class DeviceLinkedCase(BaseModel):
    id: int
    title: str
    device_model: str = ""


class DeviceLinkedSOP(BaseModel):
    id: int
    name: str
    repair_level: str = ""


class DeviceDetail(DeviceBrief):
    commissioned_at: Optional[datetime] = None
    note: str = ""
    records: List[MaintenanceRecordOut] = []      # 检修时间线（精确）
    linked_cases: List[DeviceLinkedCase] = []     # 同型号检修案例（软关联）
    linked_sops: List[DeviceLinkedSOP] = []       # 适用作业指引（软关联）
