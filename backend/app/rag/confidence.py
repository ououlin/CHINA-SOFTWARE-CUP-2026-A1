"""RAG 回答可信度评估与引用校验。"""
from __future__ import annotations

import re
from typing import Any

_REF_RE = re.compile(r"\[(\d{1,2})\]")


def validate_citations(answer: str, citation_count: int) -> dict[str, Any]:
    refs = sorted({int(x) for x in _REF_RE.findall(answer or "")})
    invalid = [r for r in refs if r < 1 or r > citation_count]
    return {
        "refs": refs,
        "has_refs": bool(refs),
        "invalid_refs": invalid,
    }


def score_confidence(
    contexts: list[dict],
    corrections: list[dict] | None = None,
    graph_lines: list[str] | None = None,
    answer: str = "",
    device: Any = None,
) -> dict[str, Any]:
    corrections = corrections or []
    graph_lines = graph_lines or []
    citation_check = validate_citations(answer, len(contexts)) if answer else {
        "refs": [], "has_refs": bool(contexts), "invalid_refs": []
    }

    score = 0.2
    reasons: list[str] = []
    warnings: list[str] = []

    if contexts:
        score += min(len(contexts), 4) * 0.08
        reasons.append(f"命中 {len(contexts)} 条检修知识片段")
        top_score = max(float(c.get("score") or 0) for c in contexts)
        if top_score >= 0.75:
            score += 0.18
            reasons.append("Top1 检索相关度较高")
        elif top_score >= 0.55:
            score += 0.1
            reasons.append("检索相关度中等")
        else:
            warnings.append("检索相关度偏低，建议结合人工经验复核")
    else:
        score -= 0.25
        warnings.append("未检索到可引用的知识片段")

    if device:
        score += 0.08
        reasons.append("已结合当前设备档案与近期维修记录")
        model = getattr(device, "device_model", "") or ""
        if model and any((c.get("device_model") or "") == model for c in contexts):
            score += 0.1
            reasons.append("命中当前设备同型号资料")

    if corrections:
        score += 0.18
        reasons.append(f"采纳 {len(corrections)} 条已确认人工修正")

    if graph_lines:
        score += 0.1
        reasons.append("知识图谱存在关联证据链")

    if answer:
        if not citation_check["has_refs"]:
            score -= 0.18
            warnings.append("回答未标注引用来源")
        if citation_check["invalid_refs"]:
            score -= 0.2
            warnings.append("回答包含不存在的引用编号")

    score = max(0.0, min(1.0, score))
    if score >= 0.75:
        level = "high"
    elif score >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "score": round(score, 2),
        "reasons": reasons,
        "warnings": warnings,
        "citation_check": citation_check,
    }
