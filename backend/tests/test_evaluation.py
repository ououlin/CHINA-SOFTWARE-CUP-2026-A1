"""Evaluation metric and dataset tests."""

import json
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

# ---- 阈值与运行记录（阶段 3：评测可复现） ----
from datetime import datetime, timezone

from evaluation.run_all import DEFAULT_DATASET, build_summary
from evaluation.thresholds import check_metrics, load_thresholds


def test_thresholds_cover_all_evaluation_groups():
    thresholds = load_thresholds()
    assert {"retrieval", "ablation", "agent", "load"} <= set(thresholds)
    for rules in thresholds.values():
        for rule in rules.values():
            assert {"min", "max"} & set(rule)


def test_threshold_gate_reports_min_and_max_violations():
    ok, failures = check_metrics({"recall_at_k": 0.5}, {"recall_at_k": {"min": 0.9}})
    assert not ok and "低于下限" in failures[0]

    ok, failures = check_metrics({"error_rate": 0.2}, {"error_rate": {"max": 0.1}})
    assert not ok and "高于上限" in failures[0]

    ok, failures = check_metrics({"recall_at_k": 0.92}, {"recall_at_k": {"min": 0.9}})
    assert ok and failures == []

    ok, failures = check_metrics({}, {"missing_metric": {"min": 0.1}})
    assert not ok and "未产出" in failures[0]


def test_run_summary_merges_checks_and_failures():
    summary = build_summary(
        results={"retrieval": {"recall_at_k": 1.0, "model_filter_accuracy": 1.0}},
        thresholds={"retrieval": {
            "recall_at_k": {"min": 0.9},
            "model_filter_accuracy": {"min": 0.95},
        }},
        git={"commit": "deadbeef", "short": "deadbeef", "branch": "main", "dirty": False},
        config={"retrieval_mode": "hybrid"},
        dataset_size=200,
        dataset_path=DEFAULT_DATASET,
        started_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
        duration=1.5,
    )
    assert summary["passed"] is True
    assert summary["failures"] == []
    assert summary["run_id"] == "20261120T000000Z"
    assert summary["checks"]["retrieval"]["passed"] is True


def test_eval_runs_endpoint_requires_privileged_role(client, admin_headers, worker_headers):
    assert client.get("/api/eval/runs", headers=worker_headers).status_code == 403
    resp = client.get("/api/eval/runs", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_eval_latest_returns_404_without_records(client, admin_headers):
    resp = client.get("/api/eval/runs/latest", headers=admin_headers)
    assert resp.status_code == 404
def test_run_all_cli_writes_summary_and_report(tmp_path, monkeypatch):
    from evaluation import run_all

    monkeypatch.setattr(run_all, "evaluate", lambda cases, top_k: (
        {"recall_at_k": 1.0, "model_filter_accuracy": 1.0}, [],
    ))
    monkeypatch.setattr(run_all, "run_ablation", lambda cases, top_k: {
        "results": [{
            "retrieval_mode": "hybrid",
            "recall_at_k": 1.0,
            "model_filter_accuracy": 1.0,
        }],
    })
    monkeypatch.setattr("sys.argv", [
        "run_all", "--output", str(tmp_path), "--no-persist", "--fail-on-threshold",
    ])

    assert run_all.main() == 0
    run_dirs = list(tmp_path.glob("run-*"))
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["dataset"]["queries"] == 200
    assert "评测报告" in (run_dirs[0] / "report.md").read_text(encoding="utf-8")