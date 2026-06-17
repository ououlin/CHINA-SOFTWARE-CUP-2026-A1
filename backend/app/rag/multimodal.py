"""多模态检索：故障图片 -> Qwen-VL 结构化研判 -> 双重校验拦截 -> 文本检索 -> 诊断。

设计：
  ① VL 输出结构化 JSON（含 is_industrial_fault 与 confidence），先做安全校验——
     模糊图 / 非设备图（地板、盒饭等）直接拦截，不进入后续检索与生成，
     避免大模型"一本正经胡编"错误检修建议（工业安全严谨性）。
  ② 通过校验后，以"图生文"对齐到统一文本向量空间，复用文本 RAG 链路生成带引用诊断。
"""
import json
import re
from typing import Iterator, Optional, Tuple

from sqlalchemy.orm import Session

from ..config import settings
from ..llm import get_llm
from ..vl import get_vl
from .pipeline import build_messages
from .retriever import retrieve

# 让 VL 输出结构化 JSON：先判定是否为工业设备故障图、给出置信度，再描述
VL_PROMPT = (
    "你是工业设备检修视觉专家。请研判这张图片是否为工业设备/部件的故障或状态图，"
    "并仅输出 JSON（不要解释、不要 Markdown 代码围栏）：\n"
    "{\n"
    '  "is_industrial_fault": true/false,   // 是否为设备/部件/铭牌/仪表/指示灯/损坏件等工业相关图\n'
    '  "confidence": 0~1,                    // 对上述判断及可诊断性的置信度\n'
    '  "device": "识别到的设备/部件，无则空",\n'
    '  "phenomena": "可见故障现象：颜色异常/变形/裂纹/积碳/泄漏/磨损/烧蚀/错误码等",\n'
    '  "keywords": ["便于检索的关键词3~6个"],\n'
    '  "description": "面向检索的简洁中文故障描述"\n'
    "}\n"
    "若图片模糊、与设备无关（如地板、食物、人像、风景），令 is_industrial_fault=false 且 confidence 给低值。"
)


class ImageRejected(Exception):
    """图片未通过双重校验（非设备故障图或置信度过低），应拦截不再检索。"""

    def __init__(self, message: str, confidence: float):
        super().__init__(message)
        self.confidence = confidence


def _extract_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e <= s:
        raise ValueError("VL 未返回 JSON")
    return json.loads(t[s:e + 1])


def analyze_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """调用 VL 做结构化研判；返回 {is_industrial_fault, confidence, description, ...}。

    VL 不按 JSON 返回时"失败开放"：当作有效图、置信度 0.7，用原文作描述，避免误拦截。
    """
    raw = get_vl().understand(image_bytes, VL_PROMPT, mime=mime)
    try:
        data = _extract_json(raw)
        return {
            "is_industrial_fault": bool(data.get("is_industrial_fault", True)),
            "confidence": float(data.get("confidence", 0.7) or 0),
            "device": (data.get("device") or "").strip(),
            "phenomena": (data.get("phenomena") or "").strip(),
            "keywords": data.get("keywords") or [],
            "description": (data.get("description") or raw).strip(),
        }
    except Exception:
        return {"is_industrial_fault": True, "confidence": 0.7,
                "device": "", "phenomena": "", "keywords": [],
                "description": (raw or "").strip()}


def guard_image(analysis: dict) -> None:
    """双重校验拦截：非设备故障 或 置信度低于阈值 -> 抛 ImageRejected。"""
    conf = analysis.get("confidence", 0.0)
    if not analysis.get("is_industrial_fault") or conf < settings.image_confidence_threshold:
        raise ImageRejected(
            "图片模糊或非设备故障，请重新拍摄设备铭牌、指示灯或损坏部件后再试。",
            confidence=round(conf, 2),
        )


def _compose_query(image_desc: str, user_text: Optional[str]) -> str:
    parts = [f"【图片识别的故障信息】\n{image_desc}"]
    if user_text:
        parts.append(f"【用户补充说明】\n{user_text}")
    return "\n\n".join(parts)


def answer_image_stream(
    db: Session,
    image_desc: str,
    user_text: Optional[str] = None,
    device_model: Optional[str] = None,
) -> Tuple[list, "callable"]:
    """已通过校验后：以图片描述检索手册并流式诊断。返回 (检索片段, 文本流生成器)。"""
    query = _compose_query(image_desc, user_text)
    contexts = retrieve(db, query, device_model=device_model)
    messages = build_messages(query, contexts)

    def gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            yield piece

    return contexts, gen
