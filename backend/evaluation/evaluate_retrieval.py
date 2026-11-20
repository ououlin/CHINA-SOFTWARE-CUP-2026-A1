"""Run the controlled 200-query retrieval benchmark and emit evidence reports."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.db import SessionLocal
from app.rag.retriever import normalize_model, retrieve


QUERY_TEMPLATES = [
    "{query}",
    "请问{query}",
    "现场设备出现问题：{query}",
    "检修时遇到{query}",
    "请给出{query}的处理依据",
    "按照维修手册，{query}",
    "老师傅想确认：{query}",
    "需要制定作业步骤：{query}",
    "设备报警后，{query}",
    "请用简洁步骤说明{query}",
]


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_cases(base_cases: Iterable[dict]) -> list[dict]:
    expanded = []
    for case in base_cases:
        for index, template in enumerate(QUERY_TEMPLATES, start=1):
            expanded.append({
                **case,
                "id": f"{case['id']}-p{index:02d}",
                "query": template.format(query=case["query"]),
                "base_id": case["id"],
            })
    return expanded


def relevance_grade(result: dict, case: dict) -> int:
    content = (result.get("content") or "").lower()
    term_hit = any(term.lower() in content for term in case["terms"])
    source_hit = result.get("doc_title") in case["sources"]
    if term_hit and source_hit:
        return 2
    if term_hit:
        return 1
    return 0


def reciprocal_rank(grades: list[int]) -> float:
    for index, grade in enumerate(grades, start=1):
        if grade > 0:
            return 1.0 / index
    return 0.0


def ndcg_at_k(grades: list[int]) -> float:
    dcg = sum(
        (2 ** grade - 1) / math.log2(index + 2)
        for index, grade in enumerate(grades)
    )
    ideal = 3.0  # each labelled case has at least one grade-2 source/term pair
    return min(1.0, dcg / ideal) if ideal else 0.0


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def evaluate(cases: list[dict], top_k: int) -> tuple[dict, list[dict]]:
    details = []
    latencies = []
    with SessionLocal() as db:
        for case in cases:
            started = time.perf_counter()
            results = retrieve(
                db, case["query"], device_model=case["device_model"], top_k=top_k,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            grades = [relevance_grade(result, case) for result in results]
            model_norm = normalize_model(case["device_model"])
            model_ok = bool(results) and all(
                normalize_model(result.get("device_model") or "") == model_norm
                for result in results
            )
            details.append({
                "id": case["id"],
                "base_id": case["base_id"],
                "query": case["query"],
                "hit": any(grade > 0 for grade in grades),
                "reciprocal_rank": reciprocal_rank(grades),
                "ndcg": ndcg_at_k(grades),
                "model_filter_ok": model_ok,
                "latency_ms": round(elapsed_ms, 2),
                "retrieved": [
                    {
                        "doc_title": result.get("doc_title"),
                        "chunk_id": result.get("chunk_id"),
                        "score": result.get("score"),
                        "grade": grade,
                        "method": result.get("retrieval_method"),
                    }
                    for result, grade in zip(results, grades)
                ],
            })

    count = len(details)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_count": count,
        "top_k": top_k,
        "database": settings.database_url.split(":", 1)[0],
        "vector_backend": settings.vector_backend,
        "retrieval_mode": settings.retrieval_mode,
        "recall_at_k": round(sum(d["hit"] for d in details) / count, 4),
        "mrr": round(statistics.fmean(d["reciprocal_rank"] for d in details), 4),
        "ndcg_at_k": round(statistics.fmean(d["ndcg"] for d in details), 4),
        "model_filter_accuracy": round(
            sum(d["model_filter_ok"] for d in details) / count, 4,
        ),
        "latency_ms_p50": round(percentile(latencies, 0.50), 2),
        "latency_ms_p95": round(percentile(latencies, 0.95), 2),
    }
    return summary, details


def markdown_report(summary: dict) -> str:
    return "\n".join([
        "# 检索评测报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 查询数量：{summary['query_count']}",
        f"- 检索模式：{summary['retrieval_mode']}",
        f"- Recall@{summary['top_k']}：{summary['recall_at_k']:.2%}",
        f"- MRR：{summary['mrr']:.4f}",
        f"- nDCG@{summary['top_k']}：{summary['ndcg_at_k']:.4f}",
        f"- 型号过滤准确率：{summary['model_filter_accuracy']:.2%}",
        f"- 检索时延 P50/P95：{summary['latency_ms_p50']:.2f} / "
        f"{summary['latency_ms_p95']:.2f} ms",
        "",
        "> 该数据集为 20 个专家定义事实的 10 种受控改写，共 200 个查询。",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("retrieval_cases.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("../evidence/evaluation"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()

    cases = expand_cases(load_cases(args.dataset))
    summary, details = evaluate(cases, args.top_k)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "retrieval-report.json").write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output / "retrieval-report.md").write_text(
        markdown_report(summary), encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.fail_on_threshold:
        passed = (
            summary["recall_at_k"] >= 0.90
            and summary["model_filter_accuracy"] >= 0.95
        )
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
