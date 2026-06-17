"""查询改写（进阶 RAG）：检索前把一线工人的口语化提问改写为规范工业术语，
提升向量召回准确率。例如「那个红灯一直闪怎么办」→「电源模块过热指示灯闪烁故障排查」。

设计：尽力而为——LLM 失败/超时/输出异常时回退原查询，绝不阻断主链路。
仅用于检索召回，喂给生成的仍是用户原问题（保持回答自然、可溯源）。
"""
from typing import List, Optional

from ..config import settings
from ..llm import get_llm

REWRITE_SYSTEM = (
    "你是工业设备检修检索助手。把一线工人口语化、省略化的提问改写为规范、"
    "利于在检修手册中做向量检索的查询：补全省略的设备/部件、把口语症状转为标准"
    "故障术语、保留关键数字与型号。只输出改写后的查询本身（一行，不超过30字），"
    "不要解释、不要加引号或前缀。"
)


def rewrite_query(query: str, history: Optional[List[dict]] = None) -> str:
    """返回改写后的检索查询；不可用时返回原 query。"""
    if not settings.query_rewrite_enabled or not query or not query.strip():
        return query

    user = query.strip()
    if history:
        last = next(
            (h["content"] for h in reversed(history)
             if h.get("role") == "user" and h.get("content")), "")
        if last:
            user = f"上文提问：{last}\n当前提问：{query}"

    try:
        out = get_llm().chat([
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": user},
        ])
        out = (out or "").strip().strip('"').strip()
        out = out.splitlines()[0].strip() if out else ""
        # 容错：空 / 过长（疑似把解释也输出了）则回退原查询
        if out and len(out) <= max(40, len(query) * 4):
            return out
    except Exception:
        pass
    return query
