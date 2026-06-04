"""多模态检索：故障图片 -> Qwen-VL 结构化描述 -> 跨模态对齐到文本检索 -> 诊断。

设计：以"图生文"将图片对齐到统一文本向量空间（最稳妥的跨模态匹配），
再复用文本 RAG 链路生成带引用的诊断结论。
"""
from typing import Iterator, Optional, Tuple

from sqlalchemy.orm import Session

from ..llm import get_llm
from ..vl import get_vl
from .pipeline import build_messages
from .retriever import retrieve

# 让 VL 输出结构化、利于检索的故障描述
VL_PROMPT = (
    "你是工业设备检修视觉专家。请仔细观察这张设备故障图片，用简洁中文输出：\n"
    "1) 设备/部件识别：图中是什么设备或部件；\n"
    "2) 可见故障现象：颜色异常、变形、裂纹、积碳、泄漏、磨损、烧蚀、错误代码等；\n"
    "3) 故障关键词：3~6 个便于检索的关键词。\n"
    "只描述图中可见信息，不要臆测；若图中有铭牌/型号/故障码文字，请准确摘录。"
)


def describe_image(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """调用 VL 模型，返回故障的结构化文本描述。"""
    return get_vl().understand(image_bytes, VL_PROMPT, mime=mime)


def _compose_query(image_desc: str, user_text: Optional[str]) -> str:
    parts = [f"【图片识别的故障信息】\n{image_desc}"]
    if user_text:
        parts.append(f"【用户补充说明】\n{user_text}")
    return "\n\n".join(parts)


def answer_image_stream(
    db: Session,
    image_bytes: bytes,
    user_text: Optional[str] = None,
    device_model: Optional[str] = None,
    mime: str = "image/jpeg",
) -> Tuple[str, list, "callable"]:
    """返回 (图片描述, 检索片段, 文本流生成器)。"""
    image_desc = describe_image(image_bytes, mime=mime)
    query = _compose_query(image_desc, user_text)
    contexts = retrieve(db, query, device_model=device_model)
    messages = build_messages(query, contexts)

    def gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            yield piece

    return image_desc, contexts, gen
