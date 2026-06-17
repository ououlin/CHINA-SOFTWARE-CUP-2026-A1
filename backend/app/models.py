"""ORM 模型。

M1：用户、文档、文档分块（含向量）、问答日志。
M3：标准化作业指引——SOP 模板、SOP 步骤、作业执行记录。
M4：知识沉淀——检修案例、知识图谱实体/关系。
M5：大模型输出标注与修正——反馈/纠正表（含纠正问题向量，用于反馈增强）。
"""
import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .db import Base


def _now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(64), default="")
    hashed_password = Column(String(256), nullable=False)
    # worker 一线人员 / auditor 审核员 / admin 管理员
    role = Column(String(16), default="worker", nullable=False)
    created_at = Column(DateTime, default=_now)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False)
    source_type = Column(String(32), default="manual")  # manual 手册 / case 案例
    device_model = Column(String(128), default="", index=True)  # 设备型号（结构化过滤）
    device_type = Column(String(128), default="", index=True)   # 设备类型
    file_path = Column(String(512), default="")
    status = Column(String(16), default="approved")  # pending / approved
    created_at = Column(DateTime, default=_now)

    chunks = relationship("DocChunk", back_populates="document",
                          cascade="all, delete-orphan")


class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    page = Column(Integer, default=0)
    # 开发期(SQLite)：以 JSON 数组存向量；生产(pgvector)：替换为 vector 列
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)

    document = relationship("Document", back_populates="chunks")


class QALog(Base):
    __tablename__ = "qa_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    query = Column(Text, nullable=False)
    modality = Column(String(16), default="text")  # text / image / model
    answer = Column(Text, default="")
    citations = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)


# ============ M3 标准化作业指引（SOP）============

class SOPTemplate(Base):
    """检修流程模板：设备类型 × 检修等级 → 一组有序步骤。"""
    __tablename__ = "sop_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    device_type = Column(String(128), default="", index=True)   # 设备类型
    device_model = Column(String(128), default="", index=True)  # 设备型号（可空，越细越优先推送）
    repair_level = Column(String(32), default="", index=True)   # 检修等级：日常保养/一级维护/二级维护/大修
    summary = Column(Text, default="")                          # 模板说明
    source = Column(String(16), default="manual")               # manual 人工编写 / ai LLM 生成
    status = Column(String(16), default="approved")             # draft 草稿 / approved 已发布
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_now)

    steps = relationship(
        "SOPStep", back_populates="template",
        order_by="SOPStep.order_no", cascade="all, delete-orphan",
    )


class SOPStep(Base):
    """流程步骤：操作要点 + 风险提示 + 所需工具 + 合规必检项。"""
    __tablename__ = "sop_steps"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("sop_templates.id"),
                         nullable=False, index=True)
    order_no = Column(Integer, default=1)        # 步骤序号（有序推进）
    title = Column(String(256), nullable=False)  # 步骤标题
    instruction = Column(Text, default="")       # 操作要点
    risk = Column(Text, default="")              # 风险提示
    tools = Column(String(512), default="")      # 所需工具（逗号分隔）
    is_required = Column(Integer, default=0)     # 1=合规必检项，完成前必须勾选确认
    checkpoint = Column(String(256), default="")  # 合规确认项文案

    template = relationship("SOPTemplate", back_populates="steps")


class SOPRun(Base):
    """作业执行记录：一次按模板执行的作业，落库前经服务端合规校验。"""
    __tablename__ = "sop_runs"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("sop_templates.id"),
                         nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    device_model = Column(String(128), default="")  # 实际作业设备型号
    checked_steps = Column(JSON, default=list)       # 已勾选确认的 step_id 列表
    status = Column(String(16), default="completed")  # completed
    note = Column(Text, default="")                  # 作业备注
    created_at = Column(DateTime, default=_now)


# ============ M4 知识沉淀（案例上传-审核-入库-入图谱）============

class RepairCase(Base):
    """检修案例/经验：一线提交 → 待审核；审核通过 → 切块入向量库 + 抽取知识图谱。"""
    __tablename__ = "repair_cases"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False)
    device_type = Column(String(128), default="", index=True)
    device_model = Column(String(128), default="", index=True)
    content = Column(Text, nullable=False)            # 案例正文 / 经验总结
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # pending 待审核 / approved 已采纳入库 / rejected 已退回
    status = Column(String(16), default="pending", index=True)
    review_note = Column(Text, default="")            # 审核意见
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # 审核通过后生成的可检索文档（source_type=case），删除案例时一并清理
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime, default=_now)
    reviewed_at = Column(DateTime, nullable=True)


class KGEntity(Base):
    """知识图谱实体：设备/部件/故障/原因/措施。按 (name, etype) 去重，跨案例共享节点。"""
    __tablename__ = "kg_entities"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    # device 设备 / part 部件 / fault 故障 / cause 原因 / measure 措施
    etype = Column(String(16), default="device", index=True)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        UniqueConstraint("name", "etype", name="uq_kg_entity_name_type"),
    )


class KGRelation(Base):
    """知识图谱关系（三元组）：src -[rel_type]-> dst，保留来源案例以支持节点溯源。"""
    __tablename__ = "kg_relations"

    id = Column(Integer, primary_key=True)
    src_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False, index=True)
    rel_type = Column(String(32), default="相关")
    dst_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False, index=True)
    source_case_id = Column(Integer, ForeignKey("repair_cases.id"),
                            nullable=True, index=True)
    created_at = Column(DateTime, default=_now)


# ============ M5 大模型输出标注与修正（反馈增强闭环）============

class LLMFeedback(Base):
    """对某条问答的人工标注：点赞/点踩 + 文字纠正。

    纠正内容沉淀为"修正知识"，其原问题经嵌入后用于召回——后续相似问题
    将优先注入该修正（轻量反馈增强），形成闭环优化。
    每个用户对同一条问答仅一条反馈（可更新）。
    """
    __tablename__ = "llm_feedbacks"

    id = Column(Integer, primary_key=True)
    qa_id = Column(Integer, ForeignKey("qa_logs.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    vote = Column(String(8), default="")          # up 点赞 / down 点踩 / 空
    correction_text = Column(Text, default="")    # 人工纠正内容
    query = Column(Text, default="")              # 冗余原问题，便于反馈增强匹配
    # 纠正所针对问题的向量（开发期 JSON；生产 pgvector），用于相似问题召回
    query_embedding = Column(JSON, nullable=True)
    status = Column(String(16), default="active")  # active 生效 / archived 已下架
    # 影子知识库发布流控：pending_review 待审(仅提交者预览) / published 已发布(全局注入) / rolled_back 已回滚
    pub_status = Column(String(16), default="pending_review")
    version = Column(Integer, default=1)            # 修正版本号，正式发布时自增，支持回滚
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


# ============ 增强 G1 设备健康档案（一机一档）============

class Device(Base):
    """设备台账：一机一档。资产编号 code 唯一，作为二维码/扫码入口标识。

    设备的检修案例/适用 SOP 按 device_type+device_model 软关联现有数据；
    报修与维修历史由 MaintenanceRecord 精确挂在 device_id 上，构成检修时间线。
    """
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)  # 资产编号（扫码标识）
    name = Column(String(128), nullable=False)                  # 设备名称
    device_type = Column(String(128), default="", index=True)
    device_model = Column(String(128), default="", index=True)
    location = Column(String(128), default="")                  # 安装位置/产线
    # normal 运行中 / repairing 维修中 / stopped 停机 / scrapped 报废
    status = Column(String(16), default="normal", index=True)
    commissioned_at = Column(DateTime, nullable=True)           # 投运日期
    note = Column(Text, default="")
    created_at = Column(DateTime, default=_now)

    records = relationship(
        "MaintenanceRecord", back_populates="device",
        order_by="MaintenanceRecord.id.desc()", cascade="all, delete-orphan",
    )


class MaintenanceRecord(Base):
    """报修 / 维修记录：精确挂在某台设备上，构成其检修时间线，
    亦为故障预警（增强 G6）提供按设备/故障的统计数据。"""
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    title = Column(String(256), nullable=False)         # 报修/故障标题
    fault_desc = Column(Text, default="")               # 故障现象描述
    handling = Column(Text, default="")                 # 处理措施
    severity = Column(String(16), default="general")    # general 一般 / serious 严重 / urgent 紧急
    # open 待处理 / processing 处理中 / done 已完成
    status = Column(String(16), default="open", index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    handler_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_now)
    done_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="records")


# ============ 进阶：操作审计日志 ============

class AuditLog(Base):
    """操作审计（进阶）：记录安全生产相关的关键操作——谁在何时对什么做了什么。
    覆盖案例审核、SOP 发布/删除、修正知识下架/恢复、设备建档/删除/报修处理。
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(64), default="")        # 冗余操作人名，便于审计展示
    action = Column(String(64), nullable=False, index=True)  # 如 case.approve / sop.publish
    target_type = Column(String(32), default="")     # case / sop / feedback / device
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")                # 操作简述
    created_at = Column(DateTime, default=_now, index=True)
