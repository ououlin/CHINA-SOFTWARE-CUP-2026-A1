"""设备健康档案路由（增强 G1 一机一档）。

每台设备一份档案：基础台账 + 报修/维修时间线（精确挂 device_id）
+ 同型号检修案例与适用 SOP（按 device_type/device_model 软关联现有数据）。
扫码报修（增强 G7）复用 /by-code/{code} 入口按资产编号定位设备。
"""
from typing import List, Optional
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..audit_log import record_audit
from ..auth import get_current_user, require_roles
from ..db import get_db
from ..rag.report_gen import generate_device_report
from ..models import (
    Device, MaintenanceRecord, RepairCase, SOPTemplate, User,
)
from ..schemas import (
    DeviceIn, DeviceBrief, DeviceDetail, DeviceLinkedCase, DeviceLinkedSOP,
    MaintenanceRecordIn, MaintenanceRecordHandle, MaintenanceRecordOut,
)

router = APIRouter(prefix="/api/devices", tags=["devices"])

_EDITOR_ROLES = ("auditor", "admin")


def _names(db: Session) -> dict:
    return {u.id: (u.display_name or u.username)
            for u in db.execute(select(User)).scalars().all()}


def _counts(db: Session, device_id: int) -> tuple:
    """返回 (累计报修数, 未结报修数)。"""
    total = db.execute(
        select(func.count(MaintenanceRecord.id))
        .where(MaintenanceRecord.device_id == device_id)
    ).scalar() or 0
    openc = db.execute(
        select(func.count(MaintenanceRecord.id))
        .where(MaintenanceRecord.device_id == device_id,
               MaintenanceRecord.status != "done")
    ).scalar() or 0
    return total, openc


def _brief(db: Session, d: Device) -> DeviceBrief:
    total, openc = _counts(db, d.id)
    return DeviceBrief(
        id=d.id, code=d.code, name=d.name, device_type=d.device_type,
        device_model=d.device_model, location=d.location, status=d.status,
        fault_count=total, open_count=openc, created_at=d.created_at,
    )


def _record_out(r: MaintenanceRecord, names: dict) -> MaintenanceRecordOut:
    return MaintenanceRecordOut(
        id=r.id, device_id=r.device_id, title=r.title, fault_desc=r.fault_desc,
        handling=r.handling, severity=r.severity, status=r.status,
        reporter_name=names.get(r.reporter_id, ""),
        handler_name=names.get(r.handler_id, ""),
        created_at=r.created_at, done_at=r.done_at,
    )


def _detail(db: Session, d: Device) -> DeviceDetail:
    names = _names(db)
    base = _brief(db, d).model_dump()

    # 报修时间线（精确）
    records = [_record_out(r, names) for r in d.records]

    # 同型号检修案例（软关联，已采纳的可检索案例）
    cstmt = select(RepairCase).where(RepairCase.status == "approved")
    if d.device_model:
        cstmt = cstmt.where(RepairCase.device_model == d.device_model)
    elif d.device_type:
        cstmt = cstmt.where(RepairCase.device_type == d.device_type)
    linked_cases = [
        DeviceLinkedCase(id=c.id, title=c.title, device_model=c.device_model)
        for c in db.execute(cstmt.order_by(RepairCase.id.desc()).limit(10)).scalars().all()
    ]

    # 适用作业指引（软关联，已发布模板）
    sstmt = select(SOPTemplate).where(SOPTemplate.status == "approved")
    if d.device_type:
        sstmt = sstmt.where(SOPTemplate.device_type == d.device_type)
    linked_sops = [
        DeviceLinkedSOP(id=s.id, name=s.name, repair_level=s.repair_level)
        for s in db.execute(sstmt.order_by(SOPTemplate.id.desc()).limit(10)).scalars().all()
    ]

    return DeviceDetail(
        **base, commissioned_at=d.commissioned_at, note=d.note,
        records=records, linked_cases=linked_cases, linked_sops=linked_sops,
    )


@router.get("", response_model=List[DeviceBrief])
def list_devices(
    status: Optional[str] = Query(None, description="normal/repairing/stopped/scrapped"),
    device_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """设备台账列表（任意登录用户可见），可按状态/类型筛选。"""
    stmt = select(Device).order_by(Device.id.desc())
    if status:
        stmt = stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    return [_brief(db, d) for d in db.execute(stmt).scalars().all()]


@router.get("/by-code/{code}", response_model=DeviceDetail)
def get_device_by_code(code: str, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """扫码报修入口：按资产编号定位设备档案。"""
    d = db.execute(select(Device).where(Device.code == code)).scalar_one_or_none()
    if not d:
        raise HTTPException(404, f"未找到资产编号为 {code} 的设备")
    return _detail(db, d)


@router.get("/{did}", response_model=DeviceDetail)
def get_device(did: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "设备不存在")
    return _detail(db, d)


@router.post("", response_model=DeviceDetail)
def create_device(body: DeviceIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """建档（审核员/管理员）。资产编号唯一。"""
    if not body.code.strip() or not body.name.strip():
        raise HTTPException(400, "资产编号与设备名称不能为空")
    dup = db.execute(
        select(Device).where(Device.code == body.code.strip())
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(400, f"资产编号 {body.code} 已存在")
    d = Device(
        code=body.code.strip(), name=body.name.strip(),
        device_type=body.device_type.strip(), device_model=body.device_model.strip(),
        location=body.location.strip(), status=body.status or "normal",
        commissioned_at=body.commissioned_at, note=body.note,
    )
    db.add(d)
    db.flush()
    record_audit(db, user, "device.create", "device", d.id,
                 f"设备建档「{d.name}」（{d.code}）")
    db.commit()
    db.refresh(d)
    return _detail(db, d)


@router.put("/{did}", response_model=DeviceDetail)
def update_device(did: int, body: DeviceIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(*_EDITOR_ROLES))):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "设备不存在")
    if body.code.strip() != d.code:
        dup = db.execute(
            select(Device).where(Device.code == body.code.strip())
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(400, f"资产编号 {body.code} 已存在")
    d.code = body.code.strip()
    d.name = body.name.strip()
    d.device_type = body.device_type.strip()
    d.device_model = body.device_model.strip()
    d.location = body.location.strip()
    d.status = body.status or "normal"
    d.commissioned_at = body.commissioned_at
    d.note = body.note
    db.commit()
    db.refresh(d)
    return _detail(db, d)


@router.delete("/{did}")
def delete_device(did: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(*_EDITOR_ROLES))):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "设备不存在")
    record_audit(db, user, "device.delete", "device", d.id,
                 f"删除设备「{d.name}」（{d.code}）")
    db.delete(d)  # 级联删除其报修记录
    db.commit()
    return {"ok": True}


# ---- 报修 / 维修记录 ----

@router.post("/{did}/records", response_model=MaintenanceRecordOut)
def add_record(did: int, body: MaintenanceRecordIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """提交报修（任意登录用户）。设备状态自动转为「维修中」。"""
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "设备不存在")
    if not body.title.strip():
        raise HTTPException(400, "报修标题不能为空")
    r = MaintenanceRecord(
        device_id=d.id, title=body.title.strip(), fault_desc=body.fault_desc,
        severity=body.severity or "general", status="open", reporter_id=user.id,
    )
    db.add(r)
    if d.status == "normal":
        d.status = "repairing"
    db.commit()
    db.refresh(r)
    return _record_out(r, _names(db))


@router.post("/records/{rid}/handle", response_model=MaintenanceRecordOut)
def handle_record(rid: int, body: MaintenanceRecordHandle,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """处理/闭环报修（审核员/管理员）。全部报修闭环后设备恢复「运行中」。"""
    r = db.get(MaintenanceRecord, rid)
    if not r:
        raise HTTPException(404, "报修记录不存在")
    r.handling = body.handling
    r.handler_id = user.id
    r.status = body.status if body.status in ("processing", "done") else "done"
    if r.status == "done":
        r.done_at = dt.datetime.utcnow()
    record_audit(db, user, "device.repair_handle", "device", r.device_id,
                 f"处理报修「{r.title}」→ {r.status}")
    db.flush()

    # 该设备无未结报修则恢复运行中
    d = db.get(Device, r.device_id)
    if d and d.status == "repairing":
        openc = db.execute(
            select(func.count(MaintenanceRecord.id))
            .where(MaintenanceRecord.device_id == d.id,
                   MaintenanceRecord.status != "done")
        ).scalar() or 0
        if openc == 0:
            d.status = "normal"
    db.commit()
    db.refresh(r)
    return _record_out(r, _names(db))


# ---- 智能检修报告（增强 G5）----

_STATUS_CN = {"normal": "运行中", "repairing": "维修中", "stopped": "停机", "scrapped": "报废"}
_SEV_CN = {"general": "一般", "serious": "严重", "urgent": "紧急"}
_REC_CN = {"open": "待处理", "processing": "处理中", "done": "已完成"}


@router.post("/{did}/report")
def device_report(did: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """生成《设备检修报告》：LLM 汇总设备台账 + 报修时间线，返回 Markdown。"""
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "设备不存在")

    device = {
        "code": d.code, "name": d.name, "device_type": d.device_type,
        "device_model": d.device_model, "location": d.location,
        "status": _STATUS_CN.get(d.status, d.status),
        "commissioned": d.commissioned_at.strftime("%Y-%m-%d") if d.commissioned_at else "",
    }
    # 时间正序（旧→新）便于汇总
    records = [{
        "title": r.title, "fault": r.fault_desc, "handling": r.handling,
        "severity": _SEV_CN.get(r.severity, r.severity),
        "status": _REC_CN.get(r.status, r.status),
        "created": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
    } for r in reversed(d.records)]

    try:
        report = generate_device_report(device, records)
    except Exception as e:
        raise HTTPException(503, f"报告生成失败（请检查大模型配置）：{e}")
    return {"device": d.name, "code": d.code, "report": report}
