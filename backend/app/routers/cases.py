"""检修案例路由（M4 知识沉淀）：上传 → 待审核 → 审核通过则入向量库 + 抽知识图谱。"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit_log import record_audit
from ..auth import get_current_user, require_roles
from ..db import get_db
from ..ingest import ingest_text
from ..kg_store import persist_extraction
from ..models import Document, KGRelation, RepairCase, User
from ..rag.kg_extract import extract_kg
from ..schemas import (
    CaseReviewReq, RepairCaseBrief, RepairCaseIn, RepairCaseOut,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])

_EDITOR_ROLES = ("auditor", "admin")


def _names(db: Session) -> dict:
    return {u.id: (u.display_name or u.username)
            for u in db.execute(select(User)).scalars().all()}


def _kg_counts(db: Session, case_id: int) -> tuple:
    rels = db.execute(
        select(KGRelation).where(KGRelation.source_case_id == case_id)
    ).scalars().all()
    ents = set()
    for r in rels:
        ents.add(r.src_id)
        ents.add(r.dst_id)
    return len(ents), len(rels)


def _brief(c: RepairCase, names: dict) -> RepairCaseBrief:
    return RepairCaseBrief(
        id=c.id, title=c.title, device_type=c.device_type,
        device_model=c.device_model, status=c.status,
        author_name=names.get(c.author_id, ""), created_at=c.created_at,
    )


def _detail(db: Session, c: RepairCase, names: dict) -> RepairCaseOut:
    ec, rc = _kg_counts(db, c.id)
    return RepairCaseOut(
        **_brief(c, names).model_dump(),
        content=c.content, review_note=c.review_note, doc_id=c.doc_id,
        entity_count=ec, relation_count=rc,
    )


@router.post("", response_model=RepairCaseOut)
def submit_case(body: RepairCaseIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """提交检修案例/经验（任意登录用户），进入待审核队列。"""
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(400, "标题与正文不能为空")
    c = RepairCase(
        title=body.title.strip(), device_type=body.device_type.strip(),
        device_model=body.device_model.strip(), content=body.content.strip(),
        author_id=user.id, status="pending",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _detail(db, c, _names(db))


@router.get("", response_model=List[RepairCaseBrief])
def list_cases(
    status: Optional[str] = Query(None, description="pending/approved/rejected"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """案例列表：一线人员仅见本人提交；审核员/管理员见全部，可按状态筛选。"""
    stmt = select(RepairCase).order_by(RepairCase.id.desc())
    if user.role not in _EDITOR_ROLES:
        stmt = stmt.where(RepairCase.author_id == user.id)
    if status:
        stmt = stmt.where(RepairCase.status == status)
    rows = db.execute(stmt).scalars().all()
    names = _names(db)
    return [_brief(c, names) for c in rows]


@router.get("/{cid}", response_model=RepairCaseOut)
def get_case(cid: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    c = db.get(RepairCase, cid)
    if not c:
        raise HTTPException(404, "案例不存在")
    if user.role not in _EDITOR_ROLES and c.author_id != user.id:
        raise HTTPException(403, "无权查看他人案例")
    return _detail(db, c, _names(db))


@router.post("/{cid}/review", response_model=RepairCaseOut)
def review_case(cid: int, body: CaseReviewReq, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """审核：approve 采纳（切块入向量库 + 抽取知识图谱）/ reject 退回。"""
    c = db.get(RepairCase, cid)
    if not c:
        raise HTTPException(404, "案例不存在")
    if c.status != "pending":
        raise HTTPException(400, f"案例已处理（当前状态：{c.status}）")

    action = (body.action or "").lower()
    if action == "reject":
        c.status = "rejected"
        c.review_note = body.note or ""
        c.reviewed_by = user.id
        c.reviewed_at = dt.datetime.utcnow()
        record_audit(db, user, "case.reject", "case", c.id, f"退回案例「{c.title}」")
        db.commit()
        db.refresh(c)
        return _detail(db, c, _names(db))

    if action != "approve":
        raise HTTPException(400, "action 仅支持 approve / reject")

    # 1) 入向量库（核心，依赖本地 embedding，离线可靠）
    try:
        doc = ingest_text(
            db, title=c.title, content=c.content,
            device_type=c.device_type, device_model=c.device_model,
            source_type="case", status="approved",
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    # 2) 抽取知识图谱（依赖云端 LLM，尽力而为：失败不阻断采纳）
    try:
        extracted = extract_kg(
            c.content, title=c.title,
            device_type=c.device_type, device_model=c.device_model,
        )
        persist_extraction(db, c.id, extracted)
    except Exception:
        pass  # KG 抽取失败时仍完成采纳入库，实体数为 0，可后续补抽

    c.status = "approved"
    c.review_note = body.note or ""
    c.reviewed_by = user.id
    c.reviewed_at = dt.datetime.utcnow()
    c.doc_id = doc.id
    record_audit(db, user, "case.approve", "case", c.id,
                 f"采纳案例「{c.title}」并入库、抽取知识图谱")
    db.commit()
    db.refresh(c)
    return _detail(db, c, _names(db))


@router.delete("/{cid}")
def delete_case(cid: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """删除案例，并清理其生成的可检索文档与图谱关系（实体保留以维持共享节点）。"""
    c = db.get(RepairCase, cid)
    if not c:
        raise HTTPException(404, "案例不存在")
    db.execute(
        KGRelation.__table__.delete().where(KGRelation.source_case_id == cid)
    )
    if c.doc_id:
        doc = db.get(Document, c.doc_id)
        if doc:
            db.delete(doc)  # 级联删除 doc_chunks
    db.delete(c)
    db.commit()
    return {"ok": True}
