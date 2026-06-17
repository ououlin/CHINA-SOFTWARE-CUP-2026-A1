"""RAG 编排：检索 -> 组装带引用的 Prompt（含多轮历史 + 反馈增强修正）-> 调 LLM 生成。"""
import time
from typing import Iterator, List, Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..llm import get_llm
from ..metrics import observe
from .feedback import retrieve_corrections
from .graph_rag import graph_context
from .query_rewrite import rewrite_query
from .retriever import retrieve

SYSTEM_PROMPT = (
    "你是工业设备检修领域的智能助手。请严格依据下方提供的【检修知识片段】回答用户问题，"
    "用中文、条理清晰地给出可执行的检修建议。"
    "引用片段内容时，在句末用 [序号] 标注来源（如 [1][2]）。"
    "若提供了【知识图谱关联】，可结合其中的设备-故障-原因-措施链条佐证与组织回答。"
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
                   history: Optional[List[dict]] = None,
                   graph_lines: Optional[List[str]] = None) -> List[dict]:
    if contexts:
        # 父子分块：喂模型用父块上下文（更完整），引用展示仍是精确子块
        ctx_text = "\n\n".join(
            f"[{i + 1}] (来源：{_source_label(c)})\n{c.get('parent_content') or c['content']}"
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
    if graph_lines:
        blocks.append("【知识图谱关联（结构化上下文）】\n" + "\n".join(graph_lines))
    blocks.append(f"【用户问题】\n{query}")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_history_messages(history),
        {"role": "user", "content": "\n\n".join(blocks)},
    ]


def _retrieval_query(query: str, history: Optional[List[dict]]) -> tuple:
    """决定检索用的查询：优先 LLM 查询改写，失败则回退指代补全。
    返回 (检索查询, 对用户展示的改写结果或 None)。"""
    rewritten = rewrite_query(query, history)
    if rewritten and rewritten != query:
        return rewritten, rewritten
    return _search_query(query, history), None


def answer(db: Session, query: str, device_model: Optional[str] = None,
           history: Optional[List[dict]] = None, user_id: Optional[int] = None) -> dict:
    search_q, rewritten = _retrieval_query(query, history)
    contexts = retrieve(db, search_q, device_model=device_model)
    corrections = retrieve_corrections(db, query, user_id)
    graph_lines = graph_context(db, search_q, contexts) if settings.graph_rag_enabled else []
    messages = build_messages(query, contexts, corrections, history, graph_lines)
    text = get_llm().chat(messages)
    return {"answer": text, "citations": contexts, "corrections": corrections,
            "rewritten_query": rewritten, "graph": graph_lines}


def answer_stream(db: Session, query: str,
                  device_model: Optional[str] = None,
                  history: Optional[List[dict]] = None,
                  user_id: Optional[int] = None):
    """返回 (contexts, corrections, rewritten_query, graph_lines, 文本流生成器)。"""
    search_q, rewritten = _retrieval_query(query, history)
    contexts = retrieve(db, search_q, device_model=device_model)
    corrections = retrieve_corrections(db, query, user_id)
    graph_lines = graph_context(db, search_q, contexts) if settings.graph_rag_enabled else []
    messages = build_messages(query, contexts, corrections, history, graph_lines)

    def gen() -> Iterator[str]:
        _t0 = time.perf_counter()
        first = True
        for piece in get_llm().stream(messages):
            if first:
                observe("llm_first_token", time.perf_counter() - _t0)
                first = False
            yield piece

    return contexts, corrections, rewritten, graph_lines, gen
