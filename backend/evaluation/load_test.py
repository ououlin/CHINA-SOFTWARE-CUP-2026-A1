"""Dependency-light concurrent HTTP/SSE load test with evidence reports."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx


DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "evidence" / "performance"


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * quantile) - 1)]


def login(base_url: str, username: str, password: str, timeout: float) -> str:
    response = httpx.post(
        f"{base_url}/api/auth/login",
        data={"username": username, "password": password},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def request_health(base_url: str, timeout: float, _token: str) -> dict:
    started = time.perf_counter()
    try:
        response = httpx.get(f"{base_url}/api/health", timeout=timeout)
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "first_event_ms": 0.0,
            "done": True,
            "sse_error": False,
            "error": "" if response.status_code == 200 else response.text[:200],
        }
    except Exception as exc:
        return {
            "ok": False, "status_code": 0,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "first_event_ms": 0.0, "done": False, "sse_error": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def request_sse(base_url: str, timeout: float, token: str) -> dict:
    started = time.perf_counter()
    first_event_ms = 0.0
    done = False
    sse_error = False
    status_code = 0
    try:
        with httpx.stream(
            "POST", f"{base_url}/api/chat/diagnose_stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "发动机怠速不稳如何排查", "device_model": "通用四冲程"},
            timeout=timeout,
        ) as response:
            status_code = response.status_code
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    if not first_event_ms:
                        first_event_ms = (time.perf_counter() - started) * 1000
                    event = line[6:].strip()
                    sse_error = sse_error or event == "error"
                    done = done or event == "done"
        return {
            "ok": done,
            "status_code": status_code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "first_event_ms": first_event_ms,
            "done": done,
            "sse_error": sse_error,
            "error": "" if done else "SSE stream ended without done event",
        }
    except Exception as exc:
        return {
            "ok": False, "status_code": status_code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "first_event_ms": first_event_ms, "done": done,
            "sse_error": sse_error,
            "error": f"{type(exc).__name__}: {exc}",
        }


def summarize(details: list[dict], mode: str, concurrency: int) -> dict:
    count = len(details)
    latencies = [item["latency_ms"] for item in details]
    first_events = [item["first_event_ms"] for item in details if item["first_event_ms"]]
    failures = sum(not item["ok"] for item in details)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "concurrency": concurrency,
        "request_count": count,
        "success_count": count - failures,
        "error_rate": round(failures / count, 4) if count else 1.0,
        "sse_error_event_rate": round(
            sum(item["sse_error"] for item in details) / count, 4,
        ) if count else 0.0,
        "latency_ms_mean": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "latency_ms_p50": round(percentile(latencies, 0.50), 2),
        "latency_ms_p95": round(percentile(latencies, 0.95), 2),
        "first_event_ms_p95": round(percentile(first_events, 0.95), 2),
    }


def markdown_report(summary: dict) -> str:
    return "\n".join([
        "# 并发与 SSE 性能报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 模式：{summary['mode']}",
        f"- 并发数 / 请求数：{summary['concurrency']} / {summary['request_count']}",
        f"- 错误率：{summary['error_rate']:.2%}",
        f"- SSE error 事件率：{summary['sse_error_event_rate']:.2%}",
        f"- 延迟 P50 / P95：{summary['latency_ms_p50']:.2f} / {summary['latency_ms_p95']:.2f} ms",
        f"- SSE 首事件 P95：{summary['first_event_ms_p95']:.2f} ms",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("health", "sse"), default="health")
    parser.add_argument("--concurrency", type=int, default=30)
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--token", default="")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error("--concurrency and --requests must be positive")

    base_url = args.base_url.rstrip("/")
    token = args.token
    if args.mode == "sse" and not token:
        token = login(base_url, args.username, args.password, args.timeout)
    operation = request_sse if args.mode == "sse" else request_health

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(operation, base_url, args.timeout, token)
            for _ in range(args.requests)
        ]
        details = [future.result() for future in as_completed(futures)]

    summary = summarize(details, args.mode, args.concurrency)
    report = {"summary": summary, "details": details}
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"load-{args.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    (args.output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (args.output / f"{stem}.md").write_text(
        markdown_report(summary), encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.fail_on_threshold and summary["error_rate"] >= 0.01:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
