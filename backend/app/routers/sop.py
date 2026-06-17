"""标准化作业指引（SOP）路由：模板管理 + AI 生成草稿 + 作业执行与合规校验。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit_log import record_audit
from ..auth import get_current_user, require_roles
from ..db import get_db
from ..models import SOPRun, SOPStep, SOPTemplate, User
from ..rag.sop_gen import generate_sop_draft
from ..schemas import (
    SOPGenerateReq, SOPRunOut, SOPRunSubmit, SOPTemplateBrief,
    SOPTemplateIn, SOPTemplateOut, StepOut,
)

router = APIRouter(prefix="/api/sop", tags=["sop"])

_EDITOR_ROLES = ("auditor", "admin")


def _brief(t: SOPTemplate) -> SOPTemplateBrief:
    return SOPTemplateBrief(
        id=t.id, name=t.name, device_type=t.device_type,
        device_model=t.device_model, repair_level=t.repair_level,
        summary=t.summary, source=t.source, status=t.status,
        step_count=len(t.steps),
    )


def _detail(t: SOPTemplate) -> SOPTemplateOut:
    return SOPTemplateOut(
        **_brief(t).model_dump(),
        steps=[StepOut.model_validate(s) for s in t.steps],
    )


def _run_out(run: SOPRun, name: str) -> SOPRunOut:
    return SOPRunOut(
        id=run.id, template_id=run.template_id, template_name=name,
        device_model=run.device_model, status=run.status,
        note=run.note, created_at=run.created_at,
    )


@router.get("/templates", response_model=List[SOPTemplateBrief])
def list_templates(
    device_type: Optional[str] = Query(None),
    repair_level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """模板列表（个性化推送：按设备类型 + 检修等级筛选）。

    一线人员仅见已发布模板；审核员/管理员可见草稿以便校核发布。
    """
    stmt = select(SOPTemplate).order_by(SOPTemplate.id.desc())
    if user.role not in _EDITOR_ROLES:
        stmt = stmt.where(SOPTemplate.status == "approved")
    if device_type:
        stmt = stmt.where(SOPTemplate.device_type == device_type)
    if repair_level:
        stmt = stmt.where(SOPTemplate.repair_level == repair_level)
    rows = db.execute(stmt).scalars().all()
    return [_brief(t) for t in rows]


@router.get("/templates/{tid}", response_model=SOPTemplateOut)
def get_template(tid: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    t = db.get(SOPTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    if t.status != "approved" and user.role not in _EDITOR_ROLES:
        raise HTTPException(403, "该流程尚未发布")
    return _detail(t)


@router.post("/templates", response_model=SOPTemplateOut)
def create_template(body: SOPTemplateIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """人工新建并直接发布一套作业流程（审核员/管理员）。"""
    if not body.steps:
        raise HTTPException(400, "至少需要一个步骤")
    t = SOPTemplate(
        name=body.name, device_type=body.device_type,
        device_model=body.device_model, repair_level=body.repair_level,
        summary=body.summary, source="manual", status="approved",
        created_by=user.id,
    )
    db.add(t)
    db.flush()
    for i, s in enumerate(body.steps, start=1):
        db.add(SOPStep(
            template_id=t.id, order_no=s.order_no or i, title=s.title,
            instruction=s.instruction, risk=s.risk, tools=s.tools,
            is_required=1 if s.is_required else 0, checkpoint=s.checkpoint,
        ))
    record_audit(db, user, "sop.create", "sop", t.id, f"新建并发布作业流程「{t.name}」")
    db.commit()
    db.refresh(t)
    return _detail(t)


@router.post("/generate", response_model=SOPTemplateOut)
def generate_template(body: SOPGenerateReq, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(*_EDITOR_ROLES))):
    """依手册检索 + LLM 生成流程草稿，落库为 draft 供校核（审核员/管理员）。"""
    try:
        draft = generate_sop_draft(
            db, device_type=body.device_type,
            repair_level=body.repair_level, device_model=body.device_model,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # LLM/网络异常
        raise HTTPException(502, f"生成失败：{e}")

    t = SOPTemplate(
        name=draft["name"], device_type=draft["device_type"],
        device_model=draft["device_model"], repair_level=draft["repair_level"],
        summary=draft["summary"], source="ai", status="draft",
        created_by=user.id,
    )
    db.add(t)
    db.flush()
    for s in draft["steps"]:
        db.add(SOPStep(
            template_id=t.id, order_no=s["order_no"], title=s["title"],
            instruction=s["instruction"], risk=s["risk"], tools=s["tools"],
            is_required=1 if s["is_required"] else 0, checkpoint=s["checkpoint"],
        ))
    db.commit()
    db.refresh(t)
    return _detail(t)


@router.post("/templates/{tid}/publish", response_model=SOPTemplateOut)
def publish_template(tid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*_EDITOR_ROLES))):
    t = db.get(SOPTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    t.status = "approved"
    record_audit(db, user, "sop.publish", "sop", t.id, f"发布作业流程「{t.name}」")
    db.commit()
    db.refresh(t)
    return _detail(t)


@router.delete("/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*_EDITOR_ROLES))):
    t = db.get(SOPTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    record_audit(db, user, "sop.delete", "sop", t.id, f"删除作业流程「{t.name}」")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/runs", response_model=SOPRunOut)
def submit_run(body: SOPRunSubmit, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """提交作业执行：服务端二次校验合规必检项，缺项即拦截。"""
    t = db.get(SOPTemplate, body.template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    if t.status != "approved":
        raise HTTPException(400, "该流程尚未发布，不能执行")

    checked = set(body.checked_step_ids or [])
    missing = [s for s in t.steps if s.is_required and s.id not in checked]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "存在未确认的合规必检项，无法完成作业",
                "missing": [
                    {"step_id": s.id, "order_no": s.order_no, "title": s.title,
                     "checkpoint": s.checkpoint or s.title}
                    for s in missing
                ],
            },
        )

    run = SOPRun(
        template_id=t.id, user_id=user.id,
        device_model=body.device_model or t.device_model,
        checked_steps=sorted(checked), status="completed", note=body.note,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _run_out(run, t.name)


@router.get("/runs", response_model=List[SOPRunOut])
def list_runs(db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """我的作业执行记录。"""
    rows = db.execute(
        select(SOPRun, SOPTemplate)
        .join(SOPTemplate, SOPRun.template_id == SOPTemplate.id)
        .where(SOPRun.user_id == user.id)
        .order_by(SOPRun.id.desc())
    ).all()
    return [_run_out(r, t.name) for r, t in rows]
