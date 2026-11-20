"""设备上下文：把一机一档和近期维修历史注入 RAG。"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, MaintenanceRecord

_STATUS_CN = {"normal": "运行中", "repairing": "维修中", "stopped": "停机", "scrapped": "报废"}
_SEV_CN = {"general": "一般", "serious": "严重", "urgent": "紧急"}
_REC_CN = {"open": "待处理", "processing": "处理中", "done": "已完成"}


def get_device(db: Session, device_id: Optional[int]) -> Optional[Device]:
    if not device_id:
        return None
    return db.get(Device, device_id)


def device_context_text(db: Session, device: Optional[Device], limit: int = 5) -> str:
    if not device:
        return ""
    lines = [
        f"设备名称：{device.name}",
        f"资产编号：{device.code}",
        f"设备类型：{device.device_type or '未填写'}",
        f"设备型号：{device.device_model or '未填写'}",
        f"安装位置：{device.location or '未填写'}",
        f"当前状态：{_STATUS_CN.get(device.status, device.status)}",
    ]
    if device.note:
        lines.append(f"备注：{device.note}")

    records = db.execute(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.device_id == device.id)
        .order_by(MaintenanceRecord.id.desc())
        .limit(limit)
    ).scalars().all()
    if records:
        lines.append("最近维修/报修记录：")
        for i, r in enumerate(records, start=1):
            created = r.created_at.strftime("%Y-%m-%d") if r.created_at else ""
            parts = [
                f"{i}. {created} {r.title}",
                f"严重度：{_SEV_CN.get(r.severity, r.severity)}",
                f"状态：{_REC_CN.get(r.status, r.status)}",
            ]
            if r.fault_desc:
                parts.append(f"故障现象：{r.fault_desc}")
            if r.handling:
                parts.append(f"处理措施：{r.handling}")
            lines.append("；".join(parts))
    else:
        lines.append("最近维修/报修记录：暂无")
    return "\n".join(lines)
