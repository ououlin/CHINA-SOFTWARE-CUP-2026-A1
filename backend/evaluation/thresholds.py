"""评测阈值的唯一来源：读取 thresholds.json 并做 min/max 判定。

设计目标：`--fail-on-threshold` 不再把 0.90 / 0.95 之类数字散落在各脚本里，
改阈值只改 JSON，CI 与本地命令共用同一套判定。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).with_name("thresholds.json")


def load_thresholds(path: Path | None = None) -> dict[str, dict[str, dict[str, float]]]:
    """读取阈值配置，返回 {分组: {指标: {"min"|"max": 数值}}}。"""
    raw = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError(f"阈值文件缺少 metrics 段：{path or DEFAULT_PATH}")
    for group, rules in metrics.items():
        if not isinstance(rules, dict):
            raise ValueError(f"阈值分组 {group} 必须是对象")
        for metric, rule in rules.items():
            if not isinstance(rule, dict) or not ({"min", "max"} & set(rule)):
                raise ValueError(f"阈值 {group}.{metric} 需要 min 或 max")
    return metrics


def check_metrics(
    summary: dict[str, Any],
    spec: dict[str, dict[str, float]],
) -> tuple[bool, list[str]]:
    """按阈值判定一组指标，返回 (是否通过, 失败原因列表)。"""
    failures: list[str] = []
    for metric, rule in spec.items():
        value = summary.get(metric)
        if value is None:
            failures.append(f"{metric} 未产出")
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            failures.append(f"{metric}={value!r} 不是数值")
            continue
        minimum = rule.get("min")
        maximum = rule.get("max")
        if minimum is not None and numeric < float(minimum):
            failures.append(f"{metric}={numeric:.4f} 低于下限 {minimum}")
        if maximum is not None and numeric > float(maximum):
            failures.append(f"{metric}={numeric:.4f} 高于上限 {maximum}")
    return (not failures, failures)
