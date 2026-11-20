"""一键评测入口：检索 → 消融 → Agent（可选）→ 负载（可选）。

一次运行产出一个可追溯的 run 目录：

    evidence/evaluation/run-20261120T081500Z/
      summary.json    机器可读：git commit、配置快照、各组指标、阈值判定
      report.md       人读：汇总表与失败项

用法（在 backend 目录下）：

    python -m evaluation.run_all                       # 检索 + 消融
    python -m evaluation.run_all --with-agent          # 追加 Agent 评测（需真实模型 Key 与种子库）
    python -m evaluation.run_all --with-load --base-url http://127.0.0.1:8000
    python -m evaluation.run_all --fail-on-threshold   # 任一阈值不达标则以 1 退出
    python -m evaluation.run_all --check-only          # 只校验数据集/阈值，CI 用

默认把运行记录写入 evaluation_runs 表，便于 /api/eval/runs 查看历史趋势；
`--no-persist` 可跳过落库（离线环境或无数据库权限时使用）。
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.evaluate_ablation import run_ablation
from evaluation.evaluate_retrieval import evaluate, expand_cases, load_cases
from evaluation.thresholds import check_metrics, load_thresholds

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = Path(__file__).with_name("retrieval_cases.json")
DEFAULT_OUTPUT = ROOT / "evidence" / "evaluation"

CONFIG_KEYS = (
    "embedding_provider",
    "embedding_model",
    "embedding_dim",
    "retrieval_mode",
    "vector_backend",
    "hybrid_rrf_k",
    "hybrid_candidate_k",
    "retrieve_top_k",
    "parent_child_enabled",
    "graph_rag_enabled",
    "query_rewrite_enabled",
    "agent_max_iterations",
)


def _git(*args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def git_state() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    return {
        "commit": commit or "unknown",
        "short": commit[:8] if commit else "unknown",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "dirty": bool(_git("status", "--porcelain")),
    }


def config_snapshot() -> dict[str, Any]:
    from app.config import settings

    return {key: getattr(settings, key) for key in CONFIG_KEYS}


def _display_path(path: Path) -> str:
    """尽量显示相对仓库根目录的路径，便于报告引用。"""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return str(path)


def build_summary(
    *,
    results: dict[str, dict[str, Any]],
    thresholds: dict[str, dict[str, dict[str, float]]],
    git: dict[str, Any],
    config: dict[str, Any],
    dataset_size: int,
    dataset_path: Path,
    started_at: datetime,
    duration: float,
) -> dict[str, Any]:
    """把各组指标与阈值判定合并成一份可序列化的运行记录。"""
    checks: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for group, spec in thresholds.items():
        if group not in results:
            continue
        passed, problems = check_metrics(results[group], spec)
        checks[group] = {"passed": passed, "failures": problems}
        failures.extend(f"{group}.{problem}" for problem in problems)
    return {
        "run_id": started_at.strftime("%Y%m%dT%H%M%SZ"),
        "created_at": started_at.isoformat(),
        "duration_seconds": round(duration, 2),
        "git": git,
        "python": platform.python_version(),
        "dataset": {
            "queries": dataset_size,
            "path": _display_path(dataset_path),
        },
        "config": config,
        "results": results,
        "checks": checks,
        "passed": not failures,
        "failures": failures,
    }


def _metric_rows(group: str, metrics: dict[str, Any]) -> list[str]:
    rows = []
    for key, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            rows.append(f"| {group} | {key} | {round(float(value), 4)} |")
    return rows


def render_report(summary: dict[str, Any]) -> str:
    """生成 Markdown 报告：环境信息 → 指标表 → 阈值判定。"""
    git = summary["git"]
    lines = [
        "# 评测报告",
        "",
        f"- run_id：`{summary['run_id']}`",
        f"- 生成时间：{summary['created_at']}（耗时 {summary['duration_seconds']}s）",
        f"- 代码版本：`{git['short']}`（分支 {git['branch']}"
        f"{'，工作区有未提交改动' if git['dirty'] else ''}）",
        f"- 数据集：{summary['dataset']['queries']} 条查询",
        f"- 运行环境：Python {summary['python']}，"
        f"Embedding={summary['config']['embedding_provider']}，"
        f"检索={summary['config']['retrieval_mode']}",
        "",
        "## 指标",
        "",
        "| 分组 | 指标 | 数值 |",
        "|---|---|---|",
    ]
    for group, metrics in summary["results"].items():
        lines.extend(_metric_rows(group, metrics))
    lines.extend(["", "## 阈值判定", ""])
    if not summary["checks"]:
        lines.append("本次未启用任何阈值分组。")
    else:
        for group, check in summary["checks"].items():
            mark = "通过" if check["passed"] else "未达标"
            lines.append(f"- **{group}**：{mark}")
            for problem in check["failures"]:
                lines.append(f"  - {problem}")
    lines.extend([
        "",
        f"**总体结论：{'通过' if summary['passed'] else '未通过'}**",
        "",
        "> 阈值定义见 `backend/evaluation/thresholds.json`；"
        "报告为自动生成，未经实测的数值不作为结论引用。",
        "",
    ])
    return "\n".join(lines)


def persist_run(summary: dict[str, Any], report_path: Path) -> None:
    """把运行记录写入 evaluation_runs 表；数据库不可用时只告警不中断。"""
    try:
        from app.db import SessionLocal
        from app.models import EvaluationRun
    except Exception as exc:  # pragma: no cover - 依赖运行环境
        print(f"[persist] 跳过落库：{exc}", file=sys.stderr)
        return
    try:
        with SessionLocal() as db:
            db.add(EvaluationRun(
                run_id=summary["run_id"],
                git_commit=summary["git"]["commit"],
                status="completed" if summary["passed"] else "failed",
                passed=bool(summary["passed"]),
                metrics={
                    "results": summary["results"],
                    "checks": summary["checks"],
                    "failures": summary["failures"],
                },
                report_path=str(report_path),
            ))
            db.commit()
        print(f"[persist] 已写入 evaluation_runs：{summary['run_id']}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - 依赖运行环境
        print(f"[persist] 落库失败（不影响评测结果）：{exc}", file=sys.stderr)


def run_agent_section() -> dict[str, Any]:
    """Agent 评测：需要真实模型 Key 与已初始化的数据库。"""
    from app.config import settings
    from app.db import SessionLocal
    from .evaluate_agent import evaluate_case, summarize as summarize_agent

    if not settings.deepseek_api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，跳过 Agent 评测")
    cases = json.loads((Path(__file__).with_name("agent_cases.json")).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        details = [evaluate_case(db, case) for case in cases]
    return summarize_agent(details)


def run_load_section(base_url: str, mode: str) -> dict[str, Any]:
    """负载评测：需要目标服务已启动。"""
    from .load_test import login, request_health, request_sse, summarize as summarize_load

    token = login(base_url, "admin", "admin123", 30.0) if mode == "sse" else ""
    operation = request_sse if mode == "sse" else request_health
    details = [operation(base_url, 30.0, token) for _ in range(30)]
    return summarize_load(details, mode, 30)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键评测并生成可追溯报告")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--with-agent", action="store_true", help="追加 Agent 评测（需真实 Key）")
    parser.add_argument("--with-load", action="store_true", help="追加负载评测（需服务已启动）")
    parser.add_argument("--load-mode", choices=("health", "sse"), default="health")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--no-persist", action="store_true", help="不写入 evaluation_runs 表")
    parser.add_argument("--fail-on-threshold", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="只校验数据集与阈值")
    args = parser.parse_args()

    thresholds = load_thresholds()
    cases = expand_cases(load_cases(args.dataset))

    if args.check_only:
        print(json.dumps({
            "ok": True,
            "queries": len(cases),
            "threshold_groups": sorted(thresholds),
        }, ensure_ascii=False, indent=2))
        return 0

    started_at = datetime.now(timezone.utc)
    clock = time.perf_counter()
    results: dict[str, Any] = {}

    retrieval_summary, _details = evaluate(cases, args.top_k)
    results["retrieval"] = retrieval_summary

    ablation_report = run_ablation(cases, args.top_k)
    hybrid = next(
        item for item in ablation_report["results"] if item["retrieval_mode"] == "hybrid"
    )
    results["ablation"] = {
        "recall_at_k": hybrid["recall_at_k"],
        "model_filter_accuracy": hybrid["model_filter_accuracy"],
        "modes": {item["retrieval_mode"]: item["recall_at_k"] for item in ablation_report["results"]},
    }

    if args.with_agent:
        try:
            results["agent"] = run_agent_section()
        except RuntimeError as exc:
            print(f"[agent] {exc}", file=sys.stderr)
    if args.with_load:
        results["load"] = run_load_section(args.base_url.rstrip("/"), args.load_mode)

    duration = time.perf_counter() - clock
    summary = build_summary(
        results=results,
        thresholds=thresholds,
        git=git_state(),
        config=config_snapshot(),
        dataset_size=len(cases),
        dataset_path=args.dataset,
        started_at=started_at,
        duration=duration,
    )

    run_dir = args.output / f"run-{summary['run_id']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "report.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(summary), encoding="utf-8")

    if not args.no_persist:
        persist_run(summary, report_path)

    print(json.dumps({
        "run_id": summary["run_id"],
        "passed": summary["passed"],
        "failures": summary["failures"],
        "summary": str(summary_path),
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))

    if args.fail_on_threshold and not summary["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
