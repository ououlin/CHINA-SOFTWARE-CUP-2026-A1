"""RAG 编排：检索 -> 组装带引用的 Prompt（含多轮历史 + 反馈增强修正）-> 调 LLM 生成。"""
from typing import Iterator, List, Optional

from sqlalchemy.orm import Session

from ..llm import get_llm
from .feedback import retrieve_corrections
from .retriever import retrieve

SYSTEM_PROMPT = (
    "你是工业设备检修领域的智能助手。请严格依据下方提供的【检修知识片段】回答用户问题，"
    "用中文、条理清晰地给出可执行的检修建议。"
    "引用片段内容时，在句末用 [序号] 标注来源（如 [1][2]）。"
    "若提供了【已确认的人工修正】，请将其作为权威依据优先采纳；与片段冲突时以人工修正为准。"
    "结合上文对话理解用户的追问（如“它”“这个故障”指代前文），保持连贯。"
    "若片段中没有相关信息，请明确说明“现有资料未覆盖该问题”，不要编造。"
)

_MAX_HISTORY = 8   # 注入生成的最多历史消息条数（约 4 轮）


def _source_label(c: dict) -> str:
    """引用来源标注：手册带页码，案例（page=0）只显示标题。"""
    page = c.get("page") or 0
    return f"{c['doc_title']} 第{page}页" if page else c["doc_title"]


def _search_query(query: str, history: Optional[List[dict]]) -> str:
    """轻量指代补全：拼接最近一条用户历史问题，提升追问检索召回。"""
    if not history:
        return query
    last_user = next(
        (h["content"] for h in reversed(history)
         if h.get("role") == "user" and h.get("content")), "")
    return f"{last_user} {query}".strip() if last_user else query


def _history_messages(history: Optional[List[dict]]) -> List[dict]:
    if not history:
        return []
    out = []
    for h in history[-_MAX_HISTORY:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            out.append({"role": h["role"], "content": h["content"]})
    return out


def build_messages(query: str, contexts: List[dict],
                   corrections: Optional[List[dict]] = None,
                   history: Optional[List[dict]] = None) -> List[dict]:
    if contexts:
        ctx_text = "\n\n".join(
            f"[{i + 1}] (来源：{_source_label(c)})\n{c['content']}"
            for i, c in enumerate(contexts)
        )
    else:
        ctx_text = "（无检索到的相关片段）"

    blocks = []
    if corrections:
        corr_text = "\n".join(
            f"- 针对相似问题「{c['query']}」的已确认修正：{c['correction_text']}"
            for c in corrections
        )
        blocks.append(f"【已确认的人工修正（权威，优先采纳）】\n{corr_text}")
    blocks.append(f"【检修知识片段】\n{ctx_text}")
    blocks.append(f"【用户问题】\n{query}")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_history_messages(history),
        {"role": "user", "content": "\n\n".join(blocks)},
    ]


def answer(db: Session, query: str, device_model: Optional[str] = None,
           history: Optional[List[dict]] = None) -> dict:
    contexts = retrieve(db, _search_query(query, history), device_model=device_model)
    corrections = retrieve_corrections(db, query)
    messages = build_messages(query, contexts, corrections, history)
    text = get_llm().chat(messages)
    return {"answer": text, "citations": contexts, "corrections": corrections}


def answer_stream(db: Session, query: str,
                  device_model: Optional[str] = None,
                  history: Optional[List[dict]] = None):
    """返回 (contexts, corrections, 文本流生成器)。"""
    contexts = retrieve(db, _search_query(query, history), device_model=device_model)
    corrections = retrieve_corrections(db, query)
    messages = build_messages(query, contexts, corrections, history)

    def gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            yield piece

    return contexts, corrections, gen
