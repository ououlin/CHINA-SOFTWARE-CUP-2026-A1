"""根据设备上下文与问题推荐可执行 SOP。"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, SOPTemplate

_CJK_RE = re.compile(r"[一-鿿]")
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", text or "").lower()


def _terms(text: str) -> set[str]:
    chars = _CJK_RE.findall(text or "")
    terms = set(a + b for a, b in zip(chars, chars[1:]))
    terms |= {w.lower() for w in _WORD_RE.findall(text or "")}
    return terms


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def recommend_sops(
    db: Session,
    query: str,
    device: Optional[Device] = None,
    device_model: Optional[str] = None,
    limit: int = 3,
) -> list[dict]:
    stmt = select(SOPTemplate).where(SOPTemplate.status == "approved")
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return []

    q_terms = _terms(query)
    model = device.device_model if device else (device_model or "")
    dtype = device.device_type if device else ""
    model_norm = _norm(model)
    dtype_norm = _norm(dtype)

    scored = []
    for t in rows:
        score = 0.0
        if model_norm and _norm(t.device_model) == model_norm:
            score += 0.55
        elif dtype_norm and _norm(t.device_type) == dtype_norm:
            score += 0.35
        elif model and t.device_model and model in t.device_model:
            score += 0.25

        text = " ".join([t.name or "", t.summary or "", t.repair_level or ""])
        score += _overlap(q_terms, _terms(text)) * 0.35
        if score <= 0:
            continue
        scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": t.id,
            "name": t.name,
            "device_type": t.device_type,
            "device_model": t.device_model,
            "repair_level": t.repair_level,
            "summary": t.summary,
            "score": round(float(score), 3),
        }
        for score, t in scored[:limit]
    ]
