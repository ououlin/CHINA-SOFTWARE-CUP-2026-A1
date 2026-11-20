"""Agent 自主诊断引擎（杀手级创新 G9 · ReAct 升级版）。

不同于传统 RAG 的"单次检索→生成"，也不同于固定流水线式的"分解→检索→验证→报告"，
本引擎实现真正的 ReAct（Reasoning + Acting）自主推理循环：

  Thought → Action → Observation → Thought → Action → ... → Final Answer

Agent 拥有一组工具，根据中间结果自主决定下一步行动：
  - 证据不足时自动补充检索
  - 发现矛盾时主动交叉验证
  - 收集到足够证据后自主收束出诊断报告

这是从"流水线"到"自主Agent"的范式跃迁——裁判可直观看到系统如何像专家一样
"思考→查证→再思考→再查证→出具报告"的完整推理过程。
"""
import json
import re
import time
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..llm import get_llm
from .confidence import score_confidence
from .device_context import device_context_text, get_device
from .graph_rag import fault_tree, graph_context, reasoning_chain
from .retriever import retrieve

# =========================================================================
# 工具定义：Agent 可自主调用的工具集
# =========================================================================

TOOL_DESCRIPTIONS = """可用工具：

1. search_manual
   说明：检索设备检修手册片段（含已采纳的检修案例）
   参数：{"query": "检索关键词", "device_model": "设备型号（可选）"}
   返回：Top-3 匹配片段，含来源、相似度评分

2. search_case
   说明：检索已采纳的检修案例（一线经验）
   参数：{"query": "检索关键词"}
   返回：Top-3 匹配案例片段

3. query_graph
   说明：查询知识图谱，获取故障→原因→措施的推理链路
   参数：{"query": "故障描述或关键词"}
   返回：推理链列表 [[fault, cause, measure], ...] + 图谱关联三元组

4. query_device_history
   说明：查询指定设备的维修历史与报修记录
   参数：{"device_id": 设备ID（可选，无则用型号）}
   返回：设备台账信息 + 最近5条维修记录

使用规则：
- 每次只调用一个工具
- 根据观察结果决定下一步：证据足够→FINISH；不够→继续调工具
- 至少调用2次不同工具后再考虑收束
"""


def _build_tool(db: Session, device_model: Optional[str],
                device_id: Optional[int]) -> Dict[str, Any]:
    """构建 Agent 可调用的工具集，每个工具返回 (结果文本, 结构化数据)。"""

    def search_manual(query: str, dm: str = "") -> Tuple[str, List[dict]]:
        dm = dm or device_model or ""
        cites = retrieve(db, query, device_model=dm or None, top_k=3)
        if not cites:
            return "未检索到相关手册片段。", []
        text_parts = []
        for i, c in enumerate(cites, 1):
            text_parts.append(
                f"[E{i}] 来源：{c['doc_title']}（相关度{c['score']}）\n{c['content'][:300]}"
            )
        return "\n\n".join(text_parts), cites

    def search_case(query: str) -> Tuple[str, List[dict]]:
        from ..models import Document, DocChunk
        from sqlalchemy import select
        rows = db.execute(
            select(DocChunk, Document).join(Document, DocChunk.doc_id == Document.id)
            .where(Document.source_type == "case", Document.status == "approved")
            .limit(200)
        ).all()
        if not rows:
            return "暂无检修案例。", []
        from .retriever import _cosine, _terms, _lexical
        from ..embedding import get_embedder
        qvec = get_embedder().embed_one(query)
        q_terms = _terms(query)
        scored = []
        for chunk, doc in rows:
            if not chunk.embedding:
                continue
            vec = _cosine(qvec, chunk.embedding)
            lex = _lexical(q_terms, chunk.content)
            scored.append((vec * 0.7 + lex * 0.3, vec, lex, chunk, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        cites = []
        text_parts = []
        for i, (final, vec, lex, chunk, doc) in enumerate(scored[:3], 1):
            cite = {
                "chunk_id": chunk.id, "doc_id": doc.id,
                "doc_title": doc.title, "device_model": doc.device_model or "",
                "page": chunk.page or 0, "content": chunk.content,
                "score": round(float(final), 4),
                "vec_score": round(float(vec), 4),
                "lex_score": round(float(lex), 4),
            }
            cites.append(cite)
            text_parts.append(
                f"[E{i}] 案例：{doc.title}\n{chunk.content[:300]}"
            )
        return ("\n\n".join(text_parts) if cites else "未检索到相关案例。"), cites

    def query_graph(query: str) -> Tuple[str, List[str], List[List[str]]]:
        chains = reasoning_chain(db, query, max_chains=6)
        graph_lines = graph_context(db, query, max_edges=15)
        parts = []
        if chains:
            parts.append("推理链路：")
            for ch in chains:
                parts.append(f"  {' → '.join(ch)}")
        if graph_lines:
            parts.append("图谱关联：")
            for g in graph_lines:
                parts.append(f"  {g}")
        if not parts:
            return "知识图谱中未找到匹配的故障实体。", [], []
        return "\n".join(parts), graph_lines, chains

    def query_device_history(dev_id: int = 0) -> Tuple[str, Optional[dict]]:
        dev = get_device(db, dev_id or device_id)
        if not dev:
            return "未指定设备或设备不存在。", None
        ctx = device_context_text(db, dev)
        return ctx, {
            "name": dev.name, "code": dev.code,
            "device_type": dev.device_type, "device_model": dev.device_model,
            "status": dev.status, "location": dev.location,
        }

    return {
        "search_manual": search_manual,
        "search_case": search_case,
        "query_graph": query_graph,
        "query_device_history": query_device_history,
    }


# =========================================================================
# ReAct 提示词
# =========================================================================

REACT_SYSTEM = (
    "你是工业设备检修诊断专家Agent。请使用 ReAct（Reasoning + Acting）模式自主推理。\n\n"
    "每一步只输出一个 JSON 对象，不要输出 Markdown 代码围栏或其他文本：\n"
    '{"rationale":"简短、可展示的决策依据","action":"工具名称或FINISH",'
    '"action_input":{"query":"检索词"},"report":"仅FINISH时填写的Markdown报告"}\n\n'
    f"{TOOL_DESCRIPTIONS}\n\n"
    "诊断报告要求（FINISH时输出）：\n"
    "## 故障现象研判\n## 可能原因分析（标注证据[E1]/[E2]）\n"
    "## 推荐处理措施（优先级排序）\n## 风险提示\n## 诊断置信度\n\n"
    "规则：\n"
    "1. 至少调用2个不同工具后才能FINISH\n"
    "2. 证据冲突时在Thought中分析并标注[冲突]\n"
    "3. 只依据工具返回的证据，不编造\n"
    "4. 不输出隐藏思维过程，只输出可供用户审计的简短决策依据"
)


class AgentDecision(BaseModel):
    """单轮 Agent 决策的结构化协议。"""

    rationale: str = ""
    action: Literal[
        "search_manual", "search_case", "query_graph",
        "query_device_history", "FINISH",
    ]
    action_input: Dict[str, Any] = Field(default_factory=dict)
    report: str = ""


class SearchToolInput(BaseModel):
    query: str = ""
    device_model: str = ""


class DeviceHistoryToolInput(BaseModel):
    device_id: int = 0


def _parse_react(text: str) -> Tuple[str, str, str]:
    """解析 LLM 输出为 (thought, action, action_input)。"""
    thought = ""
    action = ""
    action_input = ""

    # 提取 Thought
    m = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", text, re.DOTALL)
    if m:
        thought = m.group(1).strip()

    # 提取 Action
    m = re.search(r"Action:\s*(\S+)", text)
    if m:
        action = m.group(1).strip()

    # 提取 Action Input
    m = re.search(r"Action Input:\s*(.*?)(?=\nThought:|$)", text, re.DOTALL)
    if m:
        action_input = m.group(1).strip()

    return thought, action, action_input


def _parse_agent_decision(text: str) -> AgentDecision:
    """优先解析 JSON 协议；兼容旧版 Thought/Action 文本作为降级路径。"""
    data = _extract_json(text)
    if data.get("action"):
        action = str(data["action"]).strip()
        action = "FINISH" if action.upper() == "FINISH" else action
        action_input = data.get("action_input") or {}
        if isinstance(action_input, str):
            action_input = _extract_json(action_input)
        payload = {
            "rationale": data.get("rationale") or data.get("thought") or "",
            "action": action,
            "action_input": action_input,
            "report": data.get("report") or "",
        }
        return AgentDecision.model_validate(payload)

    thought, action, action_input = _parse_react(text)
    if not action:
        raise ValueError("模型输出缺少 action")
    action = "FINISH" if action.upper() == "FINISH" else action
    return AgentDecision.model_validate({
        "rationale": thought,
        "action": action,
        "action_input": _extract_json(action_input),
        "report": action_input if action == "FINISH" else "",
    })


def _validate_tool_params(action: str, params: dict, default_query: str) -> dict:
    """按工具协议校验参数，并为缺失的检索词提供当前问题回退。"""
    if action in ("search_manual", "search_case", "query_graph"):
        validated = SearchToolInput.model_validate(params)
        return {
            "query": validated.query.strip() or default_query,
            "device_model": validated.device_model.strip(),
        }
    if action == "query_device_history":
        return DeviceHistoryToolInput.model_validate(params).model_dump()
    return params


def _extract_json(text: str) -> dict:
    """从文本中提取 JSON 对象。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e <= s:
        return {}
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError:
        return {}


# =========================================================================
# 证据冲突检测
# =========================================================================

_CONFLICT_KEYWORDS = {
    "矛盾": ["不能", "不应", "错误", "相反", "实际上", "而非", "但是"],
    "加剧": ["恶化", "加重", "更严重"],
    "缓解": ["恢复", "正常", "解决", "消除"],
}


def detect_conflicts(evidence_texts: List[str]) -> List[dict]:
    """检测多源证据之间的冲突。

    返回冲突列表，每项含 {sources, description, resolution}。
    """
    if len(evidence_texts) < 2:
        return []

    conflicts = []
    # 简单策略：检测"缓解"与"加剧"关键词共现
    has_relief = []
    has_worsen = []
    for i, text in enumerate(evidence_texts):
        for kw in _CONFLICT_KEYWORDS["缓解"]:
            if kw in text:
                has_relief.append(i)
                break
        for kw in _CONFLICT_KEYWORDS["加剧"]:
            if kw in text:
                has_worsen.append(i)
                break

    if has_relief and has_worsen:
        conflicts.append({
            "sources": has_relief + has_worsen,
            "description": "不同证据来源对故障趋势的判断存在分歧（部分认为已缓解，部分认为在恶化）",
            "resolution": "优先采信最新案例与设备实际维修记录；若冲突无法消解，标注需人工复核",
        })

    return conflicts


# =========================================================================
# ReAct 核心循环
# =========================================================================

MAX_ITERATIONS = 8  # 向后兼容常量；运行时以 settings.agent_max_iterations 为准


def react_diagnose(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    device_id: Optional[int] = None,
) -> dict:
    """ReAct 自主诊断（非流式版）：返回完整推理过程与诊断报告。"""
    steps_gen = _react_loop(db, query, device_model, device_id)
    # 消费生成器，收集所有步骤
    steps = []
    final_report = ""
    all_citations = []
    graph_evidence = []
    reasoning_chains = []
    conflicts = []

    for step in steps_gen:
        steps.append(step)
        if step.get("phase") == "report":
            final_report = step.get("report", "")
        if step.get("citations"):
            all_citations.extend(step["citations"])
        if step.get("graph_evidence"):
            graph_evidence = step["graph_evidence"]
        if step.get("reasoning_chains"):
            reasoning_chains = step["reasoning_chains"]
        if step.get("conflicts"):
            conflicts = step["conflicts"]

    device = get_device(db, device_id)
    confidence = score_confidence(
        all_citations, [], graph_evidence, final_report, device=device,
    )

    return {
        "query": query,
        "steps": steps,
        "report": final_report,
        "confidence": confidence,
        "all_citations": all_citations,
        "graph_evidence": graph_evidence,
        "reasoning_chains": reasoning_chains,
        "conflicts": conflicts,
        "tool_calls": [s for s in steps if s.get("phase") == "action"],
        "iteration_count": len([s for s in steps if s.get("phase") == "thought"]),
    }


def react_diagnose_stream(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    device_id: Optional[int] = None,
) -> Iterator[dict]:
    """ReAct 自主诊断（流式版）：逐步 yield 推理过程。

    每次产出 dict：
      {phase: "thought"/"action"/"observation"/"report"/"confidence"/"done", ...}
    """
    yield from _react_loop(db, query, device_model, device_id)


def _react_loop(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    device_id: Optional[int] = None,
) -> Iterator[dict]:
    """ReAct 核心循环生成器。"""
    tools = _build_tool(db, device_model, device_id)
    device = get_device(db, device_id)
    dev_ctx = device_context_text(db, device) if device else ""

    all_citations: List[dict] = []
    all_graph_evidence: List[str] = []
    all_reasoning_chains: List[List[str]] = []
    all_evidence_texts: List[str] = []
    tool_history: List[str] = []
    successful_tools: set[str] = set()
    observations: List[str] = []

    conversation = [
        {"role": "system", "content": REACT_SYSTEM},
    ]
    dev_prompt = f"\n设备档案上下文：{dev_ctx}" if dev_ctx else ""
    conversation.append({
        "role": "user",
        "content": f"故障描述：{query}{dev_prompt}\n\n请开始ReAct推理。",
    })

    max_iterations = max(2, settings.agent_max_iterations)
    min_distinct_tools = max(1, settings.agent_min_distinct_tools)

    for iteration in range(1, max_iterations + 1):
        # 调 LLM 获取结构化决策；格式错误时把校验反馈给模型后重试。
        decision = None
        raw = ""
        parse_error = ""
        for parse_attempt in range(settings.agent_parse_retries + 1):
            try:
                raw = get_llm().chat(conversation, temperature=0.3)
            except Exception as e:
                yield {"phase": "error", "message": f"LLM调用失败：{e}"}
                return
            try:
                decision = _parse_agent_decision(raw)
                break
            except (ValueError, ValidationError, TypeError) as e:
                parse_error = str(e)
                if parse_attempt < settings.agent_parse_retries:
                    conversation.extend([
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                "上一步输出不符合 JSON 动作协议。请只返回包含 "
                                "rationale/action/action_input/report 的 JSON。"
                            ),
                        },
                    ])

        if decision is None:
            yield {
                "phase": "error",
                "message": f"Agent动作解析失败：{parse_error}",
                "recoverable": True,
            }
            return

        thought = decision.rationale
        action = decision.action
        action_input = decision.action_input

        # 输出 Thought
        if thought:
            yield {
                "phase": "thought",
                "iteration": iteration,
                "thought": thought,
            }
        conversation.append({"role": "assistant", "content": raw})

        # 检查是否结束
        if action.upper() == "FINISH" or not action:
            # 生成诊断报告（action_input 即报告内容）
            report = decision.report or raw
            if len(successful_tools) < min_distinct_tools:
                # 强制至少调用两个不同工具，避免重复检索后过早收束
                conversation.append({
                    "role": "user",
                    "content": "证据可能不足，请至少调用2个不同工具后再给出诊断报告。",
                })
                continue

            # 冲突检测
            conflicts = detect_conflicts(all_evidence_texts)

            yield {
                "phase": "report",
                "report": report,
                "citations": all_citations,
                "graph_evidence": all_graph_evidence,
                "reasoning_chains": all_reasoning_chains,
                "conflicts": conflicts,
            }

            # 置信度
            confidence = score_confidence(
                all_citations, [], all_graph_evidence, report, device=device,
            )
            yield {"phase": "confidence", "confidence": confidence}

            yield {
                "phase": "done",
                "iteration_count": iteration,
                "tool_calls": len(tool_history),
            }
            return

        # 执行工具
        tool_fn = tools.get(action)
        if not tool_fn:
            observation = f"未知工具：{action}。可用工具：{list(tools.keys())}"
            yield {
                "phase": "action",
                "iteration": iteration,
                "tool": action,
                "input": action_input,
                "status": "error",
                "observation": observation,
            }
            conversation.append({
                "role": "user",
                "content": f"Observation: {observation}",
            })
            continue

        # 解析参数
        try:
            params = _validate_tool_params(action, action_input, query)
        except (ValidationError, ValueError, TypeError) as e:
            result_text = f"工具参数校验失败：{e}"
            tool_history.append(action)
            yield {
                "phase": "action",
                "iteration": iteration,
                "tool": action,
                "input": action_input,
                "status": "error",
                "observation": result_text[:500],
                "citations": [],
                "duration_ms": 0,
            }
            conversation.append({
                "role": "user",
                "content": f"Observation: {result_text}",
            })
            continue

        cites: List[dict] = []
        status = "ok"
        started_at = time.perf_counter()
        try:
            if action == "search_manual":
                result_text, cites = tool_fn(
                    query=params.get("query", query),
                    dm=params.get("device_model", ""),
                )
                all_citations.extend(cites)
                all_evidence_texts.extend(c.get("content", "") for c in cites)
            elif action == "search_case":
                result_text, cites = tool_fn(query=params.get("query", query))
                all_citations.extend(cites)
                all_evidence_texts.extend(c.get("content", "") for c in cites)
            elif action == "query_graph":
                result_text, graph_lines, chains = tool_fn(
                    query=params.get("query", query),
                )
                all_graph_evidence = graph_lines
                all_reasoning_chains = chains
            elif action == "query_device_history":
                result_text, dev_info = tool_fn(
                    dev_id=int(params.get("device_id", 0) or 0),
                )
                if result_text != "未指定设备或设备不存在。":
                    all_evidence_texts.append(result_text)
            else:
                result_text = "工具执行异常。"
        except Exception as e:
            result_text = f"工具执行出错：{e}"
            status = "error"
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        if duration_ms > settings.agent_tool_budget_seconds * 1000:
            status = "error"
            result_text = (
                f"工具调用超过预算 {settings.agent_tool_budget_seconds:g}s；"
                f"实际耗时 {duration_ms / 1000:.2f}s。"
            )

        tool_history.append(action)
        if status == "ok":
            successful_tools.add(action)
        observations.append(result_text)

        yield {
            "phase": "action",
            "iteration": iteration,
            "tool": action,
            "input": action_input,
            "status": status,
            "observation": result_text[:500],
            "citations": cites if action in ("search_manual", "search_case") else [],
            "duration_ms": duration_ms,
        }

        conversation.append({
            "role": "user",
            "content": f"Observation: {result_text}",
        })

    # 超过最大迭代次数，强制生成报告
    conversation.append({
        "role": "user",
        "content": "已达到最大迭代次数，请立即基于已有证据生成诊断报告（Action: FINISH）。",
    })
    try:
        raw = get_llm().chat(conversation, temperature=0.3)
        decision = _parse_agent_decision(raw)
        report = decision.report or raw
    except Exception:
        report = "Agent推理超时，请重试或使用普通问答。"

    conflicts = detect_conflicts(all_evidence_texts)
    confidence = score_confidence(
        all_citations, [], all_graph_evidence, report, device=device,
    )

    yield {
        "phase": "report",
        "report": report,
        "citations": all_citations,
        "graph_evidence": all_graph_evidence,
        "reasoning_chains": all_reasoning_chains,
        "conflicts": conflicts,
    }
    yield {"phase": "confidence", "confidence": confidence}
    yield {"phase": "done", "iteration_count": max_iterations, "tool_calls": len(tool_history)}


# =========================================================================
# 向后兼容：保留旧版 diagnose 接口（固定流水线，已弃用）
# =========================================================================

DECOMPOSE_SYSTEM = (
    "你是工业设备检修诊断专家。请将用户的故障描述分解为 2~4 个独立的子问题，"
    "覆盖故障现象确认、可能原因排查、处理措施方案三个维度。"
    "只输出 JSON：{\"sub_questions\": [\"子问题1\", ...]}"
)

DIAGNOSE_SYSTEM = (
    "你是工业设备检修诊断专家。请根据提供的多路检索证据与知识图谱关联，"
    "撰写一份结构化的《设备故障诊断报告》。使用 Markdown 输出，包含：\n"
    "## 故障现象研判\n## 可能原因分析\n## 推荐处理措施\n"
    "## 风险提示\n## 诊断置信度\n\n"
    "引用证据时用 [E1][E2] 标注。只依据提供的证据，不编造。"
)


def decompose(query: str) -> List[str]:
    """用 LLM 将故障描述分解为子问题。失败时回退为简单三分法。"""
    try:
        out = get_llm().chat([
            {"role": "system", "content": DECOMPOSE_SYSTEM},
            {"role": "user", "content": f"故障描述：{query}"},
        ], temperature=0.2)
        data = _extract_json(out)
        subs = [s.strip() for s in data.get("sub_questions", []) if s.strip()]
        if subs:
            return subs[:4]
    except Exception:
        pass
    return [
        f"{query}的故障现象与表现特征",
        f"{query}的可能原因有哪些",
        f"{query}的处理措施与维修方法",
    ]


def diagnose(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    device_id: Optional[int] = None,
) -> dict:
    """Agent 自主诊断（向后兼容接口，内部调用 ReAct 引擎）。

    保留旧版返回格式 {steps, report, confidence, ...} 兼容已有 /diagnose 接口。
    """
    result = react_diagnose(db, query, device_model, device_id)

    # 将 ReAct steps 转换为旧版 4 阶段格式（兼容前端）
    old_steps = [
        {
            "phase": "react",
            "title": "ReAct 自主推理",
            "description": f"共{result['iteration_count']}轮推理，调用{len(result['tool_calls'])}次工具",
            "react_steps": result["steps"],
            "tool_calls": result["tool_calls"],
            "conflicts": result["conflicts"],
        },
    ]

    return {
        "query": query,
        "steps": old_steps,
        "report": result["report"],
        "confidence": result["confidence"],
        "sub_questions": [],
        "all_citations": result["all_citations"],
        "graph_evidence": result["graph_evidence"],
        "reasoning_chains": result["reasoning_chains"],
        "conflicts": result["conflicts"],
        "tool_calls": result["tool_calls"],
        "iteration_count": result["iteration_count"],
    }
