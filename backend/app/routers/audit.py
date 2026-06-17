"""操作审计日志查询（进阶）：审核员/管理员可查安全生产关键操作流水。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..db import get_db
from ..models import AuditLog, User
from ..schemas import AuditOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(
    action: Optional[str] = Query(None, description="按操作类型筛选，如 case.approve"),
    target_type: Optional[str] = Query(None, description="case/sop/feedback/device"),
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("auditor", "admin")),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    return db.execute(stmt.limit(limit)).scalars().all()
