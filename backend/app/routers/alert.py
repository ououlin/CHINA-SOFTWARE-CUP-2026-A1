"""故障预警·预测性维护（增强 G6）。

基于设备报修/维修记录做规则化风险评分（快、可解释），识别高风险设备与
按型号的故障分布；/advice 再调 LLM 生成预测性维护建议。
"""
import datetime as dt
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit_log import record_audit
from ..auth import get_current_user, require_roles
from ..db import get_db
from ..models import Device, MaintenanceRecord, SOPTemplate, User
from ..rag.alert_gen import generate_maintenance_advice

router = APIRouter(prefix="/api/alert", tags=["alert"])

_RECENT_DAYS = 30


def _level(score: int) -> str:
    if score >= 8:
        return "高"
    if score >= 4:
        return "中"
    return "低"


def _risk_devices(db: Session) -> List[dict]:
    """规则化风险评分：故障频次 + 近 30 天 + 严重度 + 未结，越高越危险。"""
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=_RECENT_DAYS)
    out = []
    for d in db.execute(select(Device)).scalars().all():
        recs = d.records
        total = len(recs)
        if total == 0:
            continue
        recent = sum(1 for r in recs if r.created_at and r.created_at >= cutoff)
        urgent = sum(1 for r in recs if r.severity == "urgent")
        serious = sum(1 for r in recs if r.severity == "serious")
        openc = sum(1 for r in recs if r.status != "done")
        score = total + recent * 2 + serious + urgent * 2 + openc * 2
        reason_bits = [f"累计故障 {total} 次"]
        if recent:
            reason_bits.append(f"近 30 天 {recent} 次")
        if urgent or serious:
            reason_bits.append(f"严重/紧急 {urgent + serious} 次")
        if openc:
            reason_bits.append(f"{openc} 项未结")
        out.append({
            "id": d.id, "code": d.code, "name": d.name,
            "device_model": d.device_model,
            "score": score, "level": _level(score),
            "total": total, "recent": recent,
            "urgent_serious": urgent + serious, "open": openc,
            "reason": "，".join(reason_bits),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _fault_by_model(devices: List[dict], db: Session) -> List[dict]:
    """按设备型号汇总故障次数（取风险设备的累计故障）。"""
    agg = {}
    for d in db.execute(select(Device)).scalars().all():
        n = len(d.records)
        if n == 0:
            continue
        key = d.device_model or "未分类"
        agg[key] = agg.get(key, 0) + n
    rows = [{"name": k, "value": v} for k, v in agg.items()]
    rows.sort(key=lambda x: x["value"], reverse=True)
    return rows


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    risk = _risk_devices(db)
    summary = {"high": 0, "medium": 0, "low": 0}
    for r in risk:
        summary["high" if r["level"] == "高" else
                "medium" if r["level"] == "中" else "low"] += 1
    return {
        "risk_devices": risk,
        "fault_by_model": _fault_by_model(risk, db),
        "summary": summary,
    }


@router.post("/advice")
def advice(db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """LLM 生成预测性维护建议（基于当前风险评分结果）。"""
    risk = _risk_devices(db)
    faults = _fault_by_model(risk, db)
    try:
        text = generate_maintenance_advice(risk[:6], faults)
    except Exception as e:
        raise HTTPException(503, f"建议生成失败（请检查大模型配置）：{e}")
    return {"advice": text}


@router.post("/dispatch/{device_id}")
def dispatch(device_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_roles("auditor", "admin"))):
    """闭环动作（G6→M3）：为高风险设备一键生成预防性检修派单。

    自动匹配该设备类型已发布的 SOP 模板，并在设备上创建一条「预防性维护」报修任务
    （进入设备检修队列，可由一线按作业指引执行），实现"预警→派单→作业"闭环。
    """
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "设备不存在")

    sop = db.execute(
        select(SOPTemplate)
        .where(SOPTemplate.status == "approved", SOPTemplate.device_type == d.device_type)
        .order_by(SOPTemplate.id.desc())
    ).scalars().first()

    title = f"预防性维护：{sop.name}" if sop else "预防性维护检修"
    rec = MaintenanceRecord(
        device_id=d.id, title=title,
        fault_desc="故障预警系统依风险评分自动派单，建议按匹配的标准作业指引执行预防性检修。",
        severity="general", status="open", reporter_id=user.id,
    )
    db.add(rec)
    if d.status == "normal":
        d.status = "repairing"
    record_audit(db, user, "alert.dispatch", "device", d.id, title)
    db.commit()
    db.refresh(rec)
    return {
        "ok": True, "record_id": rec.id, "device": d.name, "device_code": d.code,
        "sop_id": sop.id if sop else None, "sop_name": sop.name if sop else "",
        "matched": bool(sop),
    }
