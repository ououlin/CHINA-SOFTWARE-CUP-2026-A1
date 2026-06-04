"""RAG 编排：检索 -> 组装带引用的 Prompt -> 调 LLM 生成。"""
from typing import Iterator, List, Optional

from sqlalchemy.orm import Session

from ..llm import get_llm
from .retriever import retrieve

SYSTEM_PROMPT = (
    "你是工业设备检修领域的智能助手。请严格依据下方提供的【检修知识片段】回答用户问题，"
    "用中文、条理清晰地给出可执行的检修建议。"
    "引用片段内容时，在句末用 [序号] 标注来源（如 [1][2]）。"
    "若片段中没有相关信息，请明确说明“现有资料未覆盖该问题”，不要编造。"
)


def build_messages(query: str, contexts: List[dict]) -> List[dict]:
    if contexts:
        ctx_text = "\n\n".join(
            f"[{i + 1}] (来源：{c['doc_title']} 第{c['page']}页)\n{c['content']}"
            for i, c in enumerate(contexts)
        )
    else:
        ctx_text = "（无检索到的相关片段）"
    user_content = (
        f"【检修知识片段】\n{ctx_text}\n\n"
        f"【用户问题】\n{query}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def answer(db: Session, query: str, device_model: Optional[str] = None) -> dict:
    contexts = retrieve(db, query, device_model=device_model)
    messages = build_messages(query, contexts)
    text = get_llm().chat(messages)
    return {"answer": text, "citations": contexts}


def answer_stream(db: Session, query: str,
                  device_model: Optional[str] = None):
    """返回 (contexts, 文本流生成器)。"""
    contexts = retrieve(db, query, device_model=device_model)
    messages = build_messages(query, contexts)

    def gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            yield piece

    return contexts, gen
