"""数据驾驶舱大屏（增强 G2）：聚合各模块统计，供首页可视化。

只读聚合，不写库。返回卡片指标 + 设备状态分布 + 高故障设备榜
+ 知识图谱类型分布 + 近 7 天问答/报修趋势。
"""
import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import (
    Device, MaintenanceRecord, Document, RepairCase, SOPTemplate, SOPRun,
    QALog, LLMFeedback, KGEntity, KGRelation, User,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_DEVICE_STATUS = [
    ("normal", "运行中"), ("repairing", "维修中"),
    ("stopped", "停机"), ("scrapped", "报废"),
]
_ETYPE_LABEL = {
    "device": "设备", "part": "部件", "fault": "故障",
    "cause": "原因", "measure": "措施",
}


def _count(db: Session, model, *where) -> int:
    stmt = select(func.count(model.id))
    for w in where:
        stmt = stmt.where(w)
    return db.execute(stmt).scalar() or 0


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    # ---- 卡片指标 ----
    device_total = _count(db, Device)
    open_records = _count(db, MaintenanceRecord, MaintenanceRecord.status != "done")
    qa_total = _count(db, QALog)
    up = _count(db, LLMFeedback, LLMFeedback.vote == "up", LLMFeedback.status == "active")
    down = _count(db, LLMFeedback, LLMFeedback.vote == "down", LLMFeedback.status == "active")
    satisfaction = round(up / (up + down) * 100) if (up + down) else None

    cards = {
        "device_total": device_total,
        "open_records": open_records,
        "doc_total": _count(db, Document, Document.status == "approved"),
        "case_total": _count(db, RepairCase, RepairCase.status == "approved"),
        "case_pending": _count(db, RepairCase, RepairCase.status == "pending"),
        "sop_total": _count(db, SOPTemplate, SOPTemplate.status == "approved"),
        "sop_run_total": _count(db, SOPRun),
        "qa_total": qa_total,
        "kg_entities": _count(db, KGEntity),
        "kg_relations": _count(db, KGRelation),
        "corrections": _count(db, LLMFeedback, LLMFeedback.status == "active",
                              LLMFeedback.correction_text != ""),
        "satisfaction": satisfaction,
    }

    # ---- 设备状态分布（饼图）----
    device_status = []
    for code, label in _DEVICE_STATUS:
        c = _count(db, Device, Device.status == code)
        if c:
            device_status.append({"name": label, "value": c})

    # ---- 高故障设备榜 Top5（柱状）----
    fault_rows = db.execute(
        select(Device.name, func.count(MaintenanceRecord.id).label("c"))
        .join(MaintenanceRecord, MaintenanceRecord.device_id == Device.id)
        .group_by(Device.id)
        .order_by(func.count(MaintenanceRecord.id).desc())
        .limit(5)
    ).all()
    fault_top = [{"name": name, "count": c} for name, c in fault_rows]

    # ---- 知识图谱类型分布 ----
    kg_rows = db.execute(
        select(KGEntity.etype, func.count(KGEntity.id))
        .group_by(KGEntity.etype)
    ).all()
    kg_dist = [{"name": _ETYPE_LABEL.get(et, et), "value": c} for et, c in kg_rows]

    # ---- 近 7 天问答/报修趋势（折线）----
    # 数据按 created_at(UTC) 存储，日期轴亦用 UTC 对齐，避免本地时区错位
    today = dt.datetime.utcnow().date()
    days = [today - dt.timedelta(days=i) for i in range(6, -1, -1)]
    start = dt.datetime.combine(days[0], dt.time.min)

    def _by_day(model):
        rows = db.execute(
            select(func.date(model.created_at), func.count(model.id))
            .where(model.created_at >= start)
            .group_by(func.date(model.created_at))
        ).all()
        return {str(d): c for d, c in rows}

    qa_map = _by_day(QALog)
    rec_map = _by_day(MaintenanceRecord)
    trend = {
        "dates": [d.strftime("%m-%d") for d in days],
        "qa": [qa_map.get(str(d), 0) for d in days],
        "records": [rec_map.get(str(d), 0) for d in days],
    }

    return {
        "cards": cards,
        "device_status": device_status,
        "fault_top": fault_top,
        "kg_dist": kg_dist,
        "trend": trend,
    }
