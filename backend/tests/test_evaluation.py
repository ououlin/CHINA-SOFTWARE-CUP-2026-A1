"""Evaluation metric and dataset tests."""

from pathlib import Path

from evaluation.evaluate_retrieval import (
    expand_cases, load_cases, ndcg_at_k, reciprocal_rank, relevance_grade,
)
from evaluation.evaluate_agent import report_references_valid, summarize
from evaluation.load_test import summarize as summarize_load


def test_controlled_dataset_expands_to_200_queries():
    path = Path(__file__).parents[1] / "evaluation" / "retrieval_cases.json"
    expanded = expand_cases(load_cases(path))
    assert len(expanded) == 200
    assert len({case["id"] for case in expanded}) == 200


def test_relevance_and_ranking_metrics():
    case = {
        "sources": ["维修手册"],
        "terms": ["进气阀"],
    }
    grades = [
        relevance_grade({"doc_title": "其他资料", "content": "无关内容"}, case),
        relevance_grade({"doc_title": "维修手册", "content": "检查进气阀"}, case),
    ]
    assert grades == [0, 2]
    assert reciprocal_rank(grades) == 0.5
    assert 0 < ndcg_at_k(grades) < 1


def test_agent_reference_validation_and_summary():
    assert report_references_valid("依据手册处理。[E1][E2]", 2)
    assert not report_references_valid("无引用", 2)
    assert not report_references_valid("错误引用[E3]", 2)
    summary = summarize([{
        "completed": True,
        "protocol_valid": True,
        "citation_exists": True,
        "report_references_valid": True,
        "tool_count": 2,
        "latency_ms": 12.5,
    }])
    assert summary["completion_rate"] == 1.0
    assert summary["protocol_validity"] == 1.0
    assert summary["citation_existence_rate"] == 1.0


def test_load_summary_counts_missing_done_as_error():
    summary = summarize_load([
        {"ok": True, "sse_error": False, "latency_ms": 10, "first_event_ms": 2},
        {"ok": False, "sse_error": True, "latency_ms": 20, "first_event_ms": 3},
    ], "sse", 2)
    assert summary["error_rate"] == 0.5
    assert summary["sse_error_event_rate"] == 0.5
    assert summary["latency_ms_p95"] == 20
