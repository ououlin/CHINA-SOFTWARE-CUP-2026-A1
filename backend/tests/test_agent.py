"""Agent 诊断引擎 + 故障树 + 多跳推理 + 冲突检测 测试。"""
import json

import pytest
import app.rag.agent_diagnosis as agent_module
from app.rag.agent_diagnosis import detect_conflicts, diagnose, react_diagnose
from app.rag.graph_rag import (
    fault_tree,
    reasoning_chain,
    reasoning_chain_with_confidence,
)


# ===== G9 ReAct Agent 诊断引擎 =====


class TestReActAgent:
    """ReAct 自主诊断引擎测试。"""

    def test_react_diagnose_returns_report(self, db_session):
        """ReAct 诊断返回完整推理过程与报告。"""
        result = react_diagnose(db_session, "怠速不稳")
        assert "report" in result
        assert len(result["report"]) > 0
        assert "steps" in result
        assert "confidence" in result
        # ReAct 应有多步推理
        assert result["iteration_count"] >= 2
        # 至少调用了2次工具
        assert len(result["tool_calls"]) >= 2

    def test_react_diagnose_tool_diversity(self, db_session):
        """Agent 至少调用了2种不同工具。"""
        result = react_diagnose(db_session, "怠速不稳")
        tool_names = {s["tool"] for s in result["tool_calls"]}
        assert len(tool_names) >= 2

    def test_react_diagnose_has_thoughts(self, db_session):
        """推理过程包含 Thought 步骤。"""
        result = react_diagnose(db_session, "怠速不稳")
        thoughts = [s for s in result["steps"] if s.get("phase") == "thought"]
        assert len(thoughts) >= 2

    def test_react_diagnose_has_actions(self, db_session):
        """推理过程包含 Action 步骤。"""
        result = react_diagnose(db_session, "怠速不稳")
        actions = [s for s in result["steps"] if s.get("phase") == "action"]
        assert len(actions) >= 2

    def test_diagnose_backward_compatible(self, db_session):
        """旧版 diagnose 接口向后兼容。"""
        result = diagnose(db_session, "怠速不稳")
        assert "report" in result
        assert "steps" in result
        assert "confidence" in result
        assert "all_citations" in result

    def test_diagnose_api(self, client, worker_headers):
        """POST /api/chat/diagnose 接口。"""
        resp = client.post(
            "/api/chat/diagnose",
            json={"query": "怠速不稳"},
            headers=worker_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "report" in data
        assert "confidence" in data
        assert "qa_id" in data

    def test_tool_failure_yields_error_action_without_crashing(
        self, db_session, monkeypatch,
    ):
        """检索工具异常时应返回错误步骤，并继续安全结束推理流。"""
        original_build_tool = agent_module._build_tool

        def build_failing_tool(db, device_model, device_id):
            tools = original_build_tool(db, device_model, device_id)

            def fail_search_manual(**kwargs):
                raise RuntimeError("temporary retrieval failure")

            tools["search_manual"] = fail_search_manual
            return tools

        monkeypatch.setattr(agent_module, "_build_tool", build_failing_tool)
        steps = list(agent_module.react_diagnose_stream(db_session, "怠速不稳"))
        failed = [
            step for step in steps
            if step.get("phase") == "action"
            and step.get("tool") == "search_manual"
        ]
        assert failed
        assert failed[0]["status"] == "error"
        assert failed[0]["citations"] == []
        assert steps[-1]["phase"] == "done"

    def test_structured_decision_protocol(self):
        """JSON 动作协议应通过 Pydantic 校验并保留结构化参数。"""
        decision = agent_module._parse_agent_decision(json.dumps({
            "rationale": "先检索手册确认常见原因",
            "action": "search_manual",
            "action_input": {"query": "怠速不稳"},
            "report": "",
        }, ensure_ascii=False))
        assert decision.action == "search_manual"
        assert decision.action_input["query"] == "怠速不稳"
        assert decision.rationale

    def test_malformed_decision_is_retried_and_recovers(
        self, db_session, monkeypatch,
    ):
        """模型首轮格式错误时，应反馈协议并重试，而不是直接中断。"""
        responses = iter([
            "这不是动作协议",
            json.dumps({
                "rationale": "先查手册",
                "action": "search_manual",
                "action_input": {"query": "怠速不稳"},
                "report": "",
            }, ensure_ascii=False),
            json.dumps({
                "rationale": "再查图谱交叉验证",
                "action": "query_graph",
                "action_input": {"query": "怠速不稳"},
                "report": "",
            }, ensure_ascii=False),
            json.dumps({
                "rationale": "证据充分，生成报告",
                "action": "FINISH",
                "action_input": {},
                "report": "## 诊断报告\n依据手册与图谱完成交叉验证。[E1]",
            }, ensure_ascii=False),
        ])

        class RetryLLM:
            def chat(self, messages, temperature=0.3):
                return next(responses)

        monkeypatch.setattr(agent_module, "get_llm", lambda: RetryLLM())
        steps = list(agent_module.react_diagnose_stream(db_session, "怠速不稳"))
        assert not [s for s in steps if s.get("phase") == "error"]
        assert steps[-1]["phase"] == "done"
        actions = [s for s in steps if s.get("phase") == "action"]
        assert len(actions) == 2
        assert all("duration_ms" in action for action in actions)


# ===== G10 多跳推理链 =====


class TestMultiHopReasoning:
    """多跳推理链测试（3跳深度 + 可信度传播）。"""

    def test_reasoning_chain_basic(self, db_session):
        """推理链返回 故障→原因→措施 链路。"""
        chains = reasoning_chain(db_session, "怠速不稳")
        assert isinstance(chains, list)
        assert len(chains) > 0
        for chain in chains:
            assert len(chain) >= 2  # 至少 fault→cause

    def test_reasoning_chain_multi_hop(self, db_session):
        """多跳推理：至少有一条3节点链路（fault→cause→measure 或 fault→cause→sub_cause）。"""
        chains = reasoning_chain(db_session, "怠速不稳")
        has_3hop = any(len(chain) >= 3 for chain in chains)
        assert has_3hop, "应至少有一条3跳链路"

    def test_reasoning_chain_with_confidence(self, db_session):
        """带可信度的推理链：每条链含置信度与跳数。"""
        chains = reasoning_chain_with_confidence(db_session, "怠速不稳")
        assert isinstance(chains, list)
        assert len(chains) > 0
        for item in chains:
            assert "chain" in item
            assert "confidence" in item
            assert "hops" in item
            assert 0 < item["confidence"] <= 1.0
            # 可信度应随跳数衰减
            assert item["confidence"] <= 0.85 ** item["hops"] + 0.01

    def test_reasoning_confidence_api(self, client, worker_headers):
        """GET /api/kg/reasoning_confidence 接口。"""
        resp = client.get(
            "/api/kg/reasoning_confidence",
            params={"query": "怠速不稳"},
            headers=worker_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "chains" in data
        assert "total" in data
        if data["total"] > 0:
            item = data["chains"][0]
            assert "confidence" in item
            assert "hops" in item


# ===== G10 故障树（FTA）=====


class TestFaultTree:
    """故障树自动构建测试。"""

    def test_fault_tree_structure(self, db_session):
        """故障树返回嵌套树结构。"""
        tree = fault_tree(db_session, "怠速不稳")
        assert tree is not None
        assert "tree" in tree
        assert "stats" in tree
        assert "query" in tree

    def test_fault_tree_node_fields(self, db_session):
        """每个节点含 name/type/confidence/measures/children。"""
        tree = fault_tree(db_session, "怠速不稳")
        root = tree["tree"]
        assert "name" in root
        assert "type" in root
        assert "confidence" in root
        assert "measures" in root
        assert "children" in root
        assert root["type"] == "fault"
        assert root["confidence"] == 1.0  # 根节点可信度为1

    def test_fault_tree_confidence_decay(self, db_session):
        """子节点可信度低于根节点（衰减）。"""
        tree = fault_tree(db_session, "怠速不稳")
        root = tree["tree"]
        if root["children"]:
            for child in root["children"]:
                assert child["confidence"] <= root["confidence"]

    def test_fault_tree_stats(self, db_session):
        """统计信息含节点数/原因数/措施数。"""
        tree = fault_tree(db_session, "怠速不稳")
        stats = tree["stats"]
        assert "total_nodes" in stats
        assert "cause_nodes" in stats
        assert "measure_count" in stats
        assert "max_depth" in stats
        assert stats["total_nodes"] >= 1

    def test_fault_tree_api(self, client, worker_headers):
        """GET /api/kg/fault_tree 接口。"""
        resp = client.get(
            "/api/kg/fault_tree",
            params={"query": "怠速不稳", "max_depth": 3},
            headers=worker_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tree" in data
        assert "stats" in data

    def test_fault_tree_cnc(self, db_session):
        """数控机床故障实体也能构建故障树。"""
        tree = fault_tree(db_session, "主轴异响")
        assert tree is not None
        assert tree["tree"]["name"] == "主轴异响"


# ===== G12 证据冲突检测 =====


class TestConflictDetection:
    """证据冲突检测测试。"""

    def test_no_conflict_single_evidence(self):
        """单条证据不产生冲突。"""
        conflicts = detect_conflicts(["发动机过热需要检查散热片"])
        assert len(conflicts) == 0

    def test_no_conflict_consistent_evidence(self):
        """一致证据不产生冲突。"""
        conflicts = detect_conflicts([
            "清洗化油器后恢复正常",
            "更换火花塞后故障解决",
        ])
        assert len(conflicts) == 0

    def test_detect_conflict_relief_vs_worsen(self):
        """检测缓解与加剧共现的冲突。"""
        conflicts = detect_conflicts([
            "清洗化油器后怠速恢复正常",
            "继续运行后故障恶化，排气更严重",
        ])
        assert len(conflicts) > 0
        assert "sources" in conflicts[0]
        assert "description" in conflicts[0]
        assert "resolution" in conflicts[0]

    def test_conflict_resolution_strategy(self):
        """冲突消解策略包含采信建议。"""
        conflicts = detect_conflicts([
            "更换轴承后振动消除，恢复正常",
            "运行后发现振动加重，噪声恶化",
        ])
        assert len(conflicts) > 0
        assert "人工" in conflicts[0]["resolution"] or "最新" in conflicts[0]["resolution"]

    def test_empty_evidence_no_conflict(self):
        """空证据列表不产生冲突。"""
        assert detect_conflicts([]) == []
        assert detect_conflicts([""]) == []
