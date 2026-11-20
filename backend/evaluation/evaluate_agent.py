"""Evaluate live diagnosis-agent completion, protocol validity and citations."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import DocChunk
from app.rag.agent_diagnosis import react_diagnose
from evaluation.thresholds import check_metrics, load_thresholds


DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "evidence" / "evaluation"
REFERENCE_RE = re.compile(r"\[E(\d+)]")


def citations_exist(db, citations: list[dict]) -> bool:
    for citation in citations:
        chunk_id = citation.get("chunk_id")
        if not chunk_id:
            return False
        chunk = db.scalar(select(DocChunk).where(DocChunk.id == chunk_id))
        if chunk is None or chunk.doc_id != citation.get("doc_id"):
            return False
        if (citation.get("content") or "").strip() != (chunk.content or "").strip():
            return False
    return True


def report_references_valid(report: str, citation_count: int) -> bool:
    references = [int(value) for value in REFERENCE_RE.findall(report or "")]
    return bool(references) and all(1 <= value <= citation_count for value in references)


def evaluate_case(db, case: dict) -> dict:
    started = time.perf_counter()
    error = ""
    try:
        result = react_diagnose(
            db, case["query"], device_model=case.get("device_model"),
            device_id=case.get("device_id"),
        )
    except Exception as exc:  # report the case failure without aborting the suite
        result = {"report": "", "steps": [], "tool_calls": [], "all_citations": []}
        error = f"{type(exc).__name__}: {exc}"

    actions = result.get("tool_calls") or []
    citations = result.get("all_citations") or []
    successful_tools = {
        action.get("tool") for action in actions if action.get("status") == "ok"
    }
    protocol_valid = bool(actions) and all(
        isinstance(action.get("tool"), str)
        and isinstance(action.get("input"), dict)
        and action.get("status") in {"ok", "error"}
        and isinstance(action.get("duration_ms"), (int, float))
        for action in actions
    )
    completed = bool(result.get("report")) and len(successful_tools) >= max(
        1, settings.agent_min_distinct_tools,
    ) and not error
    return {
        "id": case["id"],
        "query": case["query"],
        "completed": completed,
        "protocol_valid": protocol_valid,
        "citation_exists": bool(citations) and citations_exist(db, citations),
        "report_references_valid": report_references_valid(
            result.get("report") or "", len(citations),
        ),
        "tool_count": len(actions),
        "distinct_successful_tools": len(successful_tools),
        "citation_count": len(citations),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "error": error,
    }


def summarize(details: list[dict]) -> dict:
    count = len(details)
    if not count:
        raise ValueError("Agent evaluation dataset is empty")
    latencies = sorted(item["latency_ms"] for item in details)
    p95_index = min(count - 1, max(0, int(count * 0.95 + 0.9999) - 1))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": count,
        "completion_rate": round(sum(d["completed"] for d in details) / count, 4),
        "protocol_validity": round(sum(d["protocol_valid"] for d in details) / count, 4),
        "citation_existence_rate": round(sum(d["citation_exists"] for d in details) / count, 4),
        "report_reference_validity": round(
            sum(d["report_references_valid"] for d in details) / count, 4,
        ),
        "mean_tool_calls": round(statistics.fmean(d["tool_count"] for d in details), 2),
        "latency_ms_p95": round(latencies[p95_index], 2),
    }


def markdown_report(summary: dict) -> str:
    return "\n".join([
        "# Agent 质量评测报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 案例数：{summary['case_count']}",
        f"- 任务完成率：{summary['completion_rate']:.2%}",
        f"- 结构化动作有效率：{summary['protocol_validity']:.2%}",
        f"- 引用存在性：{summary['citation_existence_rate']:.2%}",
        f"- 报告引用编号有效率：{summary['report_reference_validity']:.2%}",
        f"- 平均工具调用数：{summary['mean_tool_calls']:.2f}",
        f"- 端到端耗时 P95：{summary['latency_ms_p95']:.2f} ms",
        "",
        "> 本报告会实际调用当前配置的 LLM 和知识库；答辩结论须保留原始 JSON。",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=Path(__file__).with_name("agent_cases.json"),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()

    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        details = [evaluate_case(db, case) for case in cases]
    summary = summarize(details)
    report = {"summary": summary, "details": details}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "agent-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (args.output / "agent-report.md").write_text(
        markdown_report(summary), encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.fail_on_threshold:
        ok, failures = check_metrics(summary, load_thresholds()["agent"])
        for failure in failures:
            print(f"[threshold] {failure}", file=sys.stderr)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
