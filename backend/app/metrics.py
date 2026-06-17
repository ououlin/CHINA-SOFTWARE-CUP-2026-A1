"""可观测性指标（进阶）：纯 Python 内存采集 + 手动输出 Prometheus 文本格式。

零依赖（不引入 prometheus-client），暴露 /metrics 供 Prometheus 抓取：
  - http_requests_total{method,path,status}        请求数
  - http_request_duration_seconds_{sum,count}      每接口延迟（可算平均/分位）
  - rag_retrieve_seconds_{sum,count}               RAG 检索耗时
  - llm_first_token_seconds_{sum,count}            大模型首字延迟（TTFT）
线程安全；多实例可换 prometheus-client 多进程模式，指标名不变。
"""
import threading
from collections import defaultdict
from typing import Dict, Tuple

_lock = threading.Lock()
_req_count: Dict[Tuple[str, str, str], int] = defaultdict(int)
_dur_sum: Dict[str, float] = defaultdict(float)
_dur_count: Dict[str, int] = defaultdict(int)
_custom_sum: Dict[str, float] = defaultdict(float)
_custom_count: Dict[str, int] = defaultdict(int)


def record_request(method: str, path: str, status: int, dur: float) -> None:
    with _lock:
        _req_count[(method, path, str(status))] += 1
        _dur_sum[path] += dur
        _dur_count[path] += 1


def observe(name: str, dur: float) -> None:
    """记录一次自定义耗时（如 rag_retrieve、llm_first_token）。"""
    with _lock:
        _custom_sum[name] += dur
        _custom_count[name] += 1


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render() -> str:
    lines = [
        "# HELP http_requests_total 累计 HTTP 请求数",
        "# TYPE http_requests_total counter",
    ]
    with _lock:
        for (m, p, s), n in _req_count.items():
            lines.append(
                f'http_requests_total{{method="{_esc(m)}",path="{_esc(p)}",status="{s}"}} {n}')
        lines.append("# TYPE http_request_duration_seconds summary")
        for p, total in _dur_sum.items():
            lines.append(f'http_request_duration_seconds_sum{{path="{_esc(p)}"}} {total:.6f}')
            lines.append(f'http_request_duration_seconds_count{{path="{_esc(p)}"}} {_dur_count[p]}')
        for name, total in _custom_sum.items():
            lines.append(f"# TYPE {name}_seconds summary")
            lines.append(f"{name}_seconds_sum {total:.6f}")
            lines.append(f"{name}_seconds_count {_custom_count[name]}")
    return "\n".join(lines) + "\n"
