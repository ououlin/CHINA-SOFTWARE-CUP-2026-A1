"""Deterministic safety controls for untrusted knowledge and operational advice."""

from __future__ import annotations

import re


_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"reveal\s+(the\s+)?system\s+prompt",
        r"system\s*prompt\s*[:：]",
        r"developer\s+message\s*[:：]",
        r"忽略(之前|以上|所有).{0,8}(指令|要求|规则)",
        r"输出.{0,8}(系统提示词|系统指令)",
        r"你现在是.{0,20}(不受限制|管理员|开发者模式)",
    )
]

_HIGH_RISK_RULES = {
    "electrical": ("高压", "带电", "触电", "配电柜", "变频器母线"),
    "pressure": ("带压", "泄压", "储气罐", "安全阀", "高压气体"),
    "mechanical": ("拆卸主轴", "吊装", "高速旋转", "防护罩", "联轴器"),
    "thermal": ("高温", "过热", "烫伤", "明火"),
    "chemical": ("有毒", "腐蚀", "清洗剂", "废油", "切削液"),
}


def detect_prompt_injection(text: str) -> list[str]:
    return [pattern.pattern for pattern in _INJECTION_PATTERNS if pattern.search(text or "")]


def validate_knowledge_text(text: str) -> None:
    hits = detect_prompt_injection(text)
    if hits:
        raise ValueError("知识文本包含疑似提示注入指令，已拒绝入库并要求人工复核")


def assess_operational_risk(text: str) -> dict:
    matched = []
    lowered = (text or "").lower()
    for category, keywords in _HIGH_RISK_RULES.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            matched.append(category)
    level = "high" if len(matched) >= 2 else "medium" if matched else "low"
    return {
        "level": level,
        "requires_human_confirmation": bool(matched),
        "categories": matched,
        "message": (
            "涉及高风险检修操作，执行前必须由具备资质的人员完成停机、断电、泄压和现场确认。"
            if matched else "未识别到需要额外人工确认的高风险操作。"
        ),
    }

