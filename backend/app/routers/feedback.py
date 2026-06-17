"""反馈/标注路由（M5）：点赞点踩 + 文字纠正；纠正沉淀为修正知识用于反馈增强。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit_log import record_audit
from ..auth import get_current_user, require_roles
from ..db import get_db
from ..embedding import get_embedder
from ..models import LLMFeedback, QALog, User
from ..schemas import FeedbackIn, FeedbackOut, FeedbackStats

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

_EDITOR_ROLES = ("auditor", "admin")
_VALID_VOTES = ("", "up", "down")


def _names(db: Session) -> dict:
    return {u.id: (u.display_name or u.username)
            for u in db.execute(select(User)).scalars().all()}


def _out(f: LLMFeedback, names: dict) -> FeedbackOut:
    return FeedbackOut(
        id=f.id, qa_id=f.qa_id, vote=f.vote or "",
        correction_text=f.correction_text or "", query=f.query or "",
        status=f.status, user_name=names.get(f.user_id, ""),
        created_at=f.created_at,
    )


@router.post("", response_model=FeedbackOut)
def submit_feedback(body: FeedbackIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """提交/更新对某条问答的反馈：点赞点踩与纠正可分别独立更新。"""
    if body.vote is None and body.correction_text is None:
        raise HTTPException(400, "请至少提供 vote 或 correction_text")
    if body.vote is not None and body.vote not in _VALID_VOTES:
        raise HTTPException(400, "vote 仅支持 up / down")

    qa = db.get(QALog, body.qa_id)
    if not qa:
        raise HTTPException(404, "问答记录不存在")

    fb = db.execute(
        select(LLMFeedback).where(
            LLMFeedback.qa_id == body.qa_id,
            LLMFeedback.user_id == user.id,
        )
    ).scalar_one_or_none()
    if not fb:
        fb = LLMFeedback(qa_id=body.qa_id, user_id=user.id, query=qa.query)
        db.add(fb)

    fb.query = qa.query
    fb.status = "active"
    if body.vote is not None:
        fb.vote = body.vote
    if body.correction_text is not None:
        corr = body.correction_text.strip()
        fb.correction_text = corr
        # 维护"纠正问题"向量：有纠正则嵌入原问题供反馈增强召回，清除则置空
        fb.query_embedding = get_embedder().embed_one(qa.query) if corr else None

    db.commit()
    db.refresh(fb)
    return _out(fb, _names(db))


@router.get("", response_model=List[FeedbackOut])
def list_feedback(
    only_corrections: bool = Query(False, description="仅看含纠正的反馈"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """反馈列表：一线人员看本人；审核员/管理员看全部（用于修正知识治理）。"""
    stmt = select(LLMFeedback).order_by(LLMFeedback.id.desc())
    if user.role not in _EDITOR_ROLES:
        stmt = stmt.where(LLMFeedback.user_id == user.id)
    if only_corrections:
        stmt = stmt.where(LLMFeedback.correction_text != "")
    rows = db.execute(stmt).scalars().all()
    names = _names(db)
    return [_out(f, names) for f in rows]


@router.get("/stats", response_model=FeedbackStats)
def feedback_stats(db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """满意度与修正知识统计（全局）。"""
    rows = db.execute(select(LLMFeedback)).scalars().all()
    up = sum(1 for f in rows if f.vote == "up")
    down = sum(1 for f in rows if f.vote == "down")
    corrections = sum(1 for f in rows
                      if f.correction_text and f.status == "active")
    return FeedbackStats(up=up, down=down, corrections=corrections)


@router.post("/{fid}/archive", response_model=FeedbackOut)
def archive_feedback(fid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """下架不当纠正：状态置 archived，不再参与反馈增强（审核员/管理员）。"""
    f = db.get(LLMFeedback, fid)
    if not f:
        raise HTTPException(404, "反馈不存在")
    f.status = "archived"
    record_audit(db, user, "feedback.archive", "feedback", f.id,
                 f"下架修正知识 #{f.id}（移出反馈增强闭环）")
    db.commit()
    db.refresh(f)
    return _out(f, _names(db))


@router.post("/{fid}/restore", response_model=FeedbackOut)
def restore_feedback(fid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """恢复已下架的纠正，重新参与反馈增强（审核员/管理员）。"""
    f = db.get(LLMFeedback, fid)
    if not f:
        raise HTTPException(404, "反馈不存在")
    f.status = "active"
    record_audit(db, user, "feedback.restore", "feedback", f.id,
                 f"恢复修正知识 #{f.id}")
    db.commit()
    db.refresh(f)
    return _out(f, _names(db))
