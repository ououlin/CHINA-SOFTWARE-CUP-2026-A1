"""个性化推送：依据检索到的检修手册片段，调用 LLM 生成标准化作业流程（SOP）草稿。

产出结构化 JSON（步骤数组），落库为 status=draft 的模板，供审核员校核后发布。
"""
import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..llm import get_llm
from .retriever import retrieve

SOP_SYSTEM = (
    "你是工业设备检修工艺专家。请依据提供的【检修手册片段】，为指定设备与检修等级"
    "编写一份标准化作业流程（SOP）。要求：步骤有序、动作明确、可执行；"
    "对存在安全或质量风险的关键步骤，标记为必检项并给出确认项文案。"
    "只输出 JSON，不要输出任何解释文字或 Markdown 代码围栏。"
)

JSON_SPEC = (
    "请严格按以下 JSON 对象格式输出：\n"
    "{\n"
    '  "name": "流程名称",\n'
    '  "summary": "一句话流程说明",\n'
    '  "steps": [\n'
    '    {"title": "步骤标题", "instruction": "操作要点", '
    '"risk": "风险提示，无则空字符串", "tools": "所需工具，逗号分隔", '
    '"is_required": true, "checkpoint": "合规确认项文案，必检项必填"}\n'
    "  ]\n"
    "}\n"
    "生成 5~8 个步骤；is_required 为 true 的步骤必须给出明确的 checkpoint。"
)


def _extract_json(text: str) -> dict:
    """从 LLM 输出中稳健提取 JSON 对象（容忍代码围栏与前后缀文字）。"""
    if not text or not text.strip():
        raise ValueError("LLM 未返回内容")
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 输出不含 JSON 对象")
    return json.loads(t[start:end + 1])


def generate_sop_draft(
    db: Session,
    device_type: str,
    repair_level: str = "二级维护",
    device_model: Optional[str] = None,
) -> dict:
    """检索手册 -> 提示 LLM -> 解析为可落库的模板草稿 dict。"""
    query = f"{device_type} {repair_level} 检修作业步骤 操作规程 安全注意事项 所需工具"
    contexts = retrieve(db, query, device_model=device_model, top_k=6)
    ctx_text = "\n\n".join(
        f"[{i + 1}] {c['content']}" for i, c in enumerate(contexts)
    ) or "（未检索到相关手册片段，请基于通用检修常识稳妥生成）"

    user_content = (
        f"设备类型：{device_type}\n"
        f"设备型号：{device_model or '通用'}\n"
        f"检修等级：{repair_level}\n\n"
        f"【检修手册片段】\n{ctx_text}\n\n{JSON_SPEC}"
    )
    messages = [
        {"role": "system", "content": SOP_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    data = _extract_json(get_llm().chat(messages, temperature=0.4))

    steps = []
    for i, s in enumerate(data.get("steps", []), start=1):
        title = (s.get("title") or "").strip()
        if not title:
            continue
        steps.append({
            "order_no": i,
            "title": title[:256],
            "instruction": (s.get("instruction") or "").strip(),
            "risk": (s.get("risk") or "").strip(),
            "tools": (s.get("tools") or "").strip()[:512],
            "is_required": bool(s.get("is_required")),
            "checkpoint": (s.get("checkpoint") or "").strip()[:256],
        })
    if not steps:
        raise ValueError("LLM 未生成有效步骤，请重试")

    return {
        "name": (data.get("name") or f"{device_type}·{repair_level}作业流程").strip()[:256],
        "device_type": device_type,
        "device_model": device_model or "",
        "repair_level": repair_level,
        "summary": (data.get("summary") or "").strip(),
        "steps": steps,
        "citations": contexts,
    }
