"""Compare vector, lexical and hybrid retrieval with the same labelled queries."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from evaluation.evaluate_retrieval import evaluate, expand_cases, load_cases
from evaluation.thresholds import check_metrics, load_thresholds


MODES = ("vector", "lexical", "hybrid")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "evidence" / "evaluation"


def run_ablation(cases: list[dict], top_k: int) -> dict:
    original_mode = settings.retrieval_mode
    results = []
    try:
        for mode in MODES:
            settings.retrieval_mode = mode
            summary, _ = evaluate(cases, top_k)
            results.append(summary)
    finally:
        settings.retrieval_mode = original_mode

    hybrid = next(item for item in results if item["retrieval_mode"] == "hybrid")
    best_single = max(
        item["recall_at_k"] for item in results
        if item["retrieval_mode"] != "hybrid"
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_count": len(cases),
        "top_k": top_k,
        "results": results,
        "hybrid_recall_gain": round(hybrid["recall_at_k"] - best_single, 4),
    }


def markdown_report(report: dict) -> str:
    lines = [
        "# 检索消融实验报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 查询数量：{report['query_count']}",
        f"- Hybrid 相对最佳单路 Recall 增益：{report['hybrid_recall_gain']:+.2%}",
        "",
        "| 模式 | Recall@K | MRR | nDCG@K | 型号过滤 | P50(ms) | P95(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        lines.append(
            f"| {item['retrieval_mode']} | {item['recall_at_k']:.2%} | "
            f"{item['mrr']:.4f} | {item['ndcg_at_k']:.4f} | "
            f"{item['model_filter_accuracy']:.2%} | "
            f"{item['latency_ms_p50']:.2f} | {item['latency_ms_p95']:.2f} |"
        )
    lines.extend([
        "",
        "> 三种模式使用同一数据库、同一查询集和同一 Top-K 顺序执行。生产结论应在 PostgreSQL + pgvector 上生成。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path,
        default=Path(__file__).with_name("retrieval_cases.json"),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()

    cases = expand_cases(load_cases(args.dataset))
    report = run_ablation(cases, args.top_k)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "retrieval-ablation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (args.output / "retrieval-ablation.md").write_text(
        markdown_report(report), encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    hybrid = next(
        item for item in report["results"] if item["retrieval_mode"] == "hybrid"
    )
    if args.fail_on_threshold:
        ok, failures = check_metrics(hybrid, load_thresholds()["ablation"])
        for failure in failures:
            print(f"[threshold] hybrid.{failure}", file=sys.stderr)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
