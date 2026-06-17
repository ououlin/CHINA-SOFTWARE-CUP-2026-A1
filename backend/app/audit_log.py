"""操作审计（进阶）：record_audit 在关键安全操作处埋点，只 add 不 commit，
随调用方所在事务一并提交，确保审计与业务操作原子一致。
"""
from typing import Optional

from sqlalchemy.orm import Session

from .models import AuditLog, User


def record_audit(db: Session, user: Optional[User], action: str,
                 target_type: str = "", target_id: Optional[int] = None,
                 detail: str = "") -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=(user.display_name or user.username) if user else "",
        action=action, target_type=target_type, target_id=target_id, detail=detail,
    ))
