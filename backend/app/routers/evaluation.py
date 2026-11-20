"""量化评测运行记录的只读查询接口。

数据由 `python -m evaluation.run_all` 写入 evaluation_runs 表，
这里只做展示：管理员/审核员可查看历史指标与阈值判定结果。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..db import get_db
from ..models import EvaluationRun, User
from ..schemas import EvaluationRunOut

router = APIRouter(prefix="/api/eval", tags=["evaluation"])


@router.get("/runs", response_model=List[EvaluationRunOut])
def list_runs(
    limit: int = Query(20, ge=1, le=100, description="返回最近的 N 次评测"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("auditor", "admin")),
):
    stmt = select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/runs/latest", response_model=Optional[EvaluationRunOut])
def latest_run(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("auditor", "admin")),
):
    stmt = select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(1)
    run = db.execute(stmt).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="尚未产生评测记录")
    return run
