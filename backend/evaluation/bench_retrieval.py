"""合成语料上的检索基准：用于量化 SQLite / 应用层检索的延迟与召回，可离线复现。

不依赖任何外部模型：用「字符 bigram 哈希」构造确定性伪嵌入，
同一条查询在同一台机器上多次运行结果一致，方便比较优化前后。

用法（在 backend 目录下）：

    python -m evaluation.bench_retrieval --chunks 10000 --queries 50
    python -m evaluation.bench_retrieval --chunks 10000 --queries 50 --fail-on-threshold

输出：evidence/performance/bench-<时间戳>.json（含 p50/p95、Recall@k、参数快照）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from evaluation.thresholds import check_metrics, load_thresholds

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "evidence" / "performance"

DEVICE_MODELS = ("CK6140", "LS25-132", "WY125", "CNC-01", "KX-200")
FAULTS = (
    "主轴异响", "排气压力不足", "怠速不稳", "液压油温过高", "导轨润滑不良",
    "伺服过流", "轴承磨损", "冷却液泄漏", "进气阀卡滞", "联轴器松动",
)
MEASURES = (
    "检查轴承滚道与润滑状态并更换损坏件", "清洗进气阀与滤芯", "调整化油器怠速油路",
    "更换密封圈并补充液压油", "校正导轨预紧力", "紧固联轴器螺栓并复测同心度",
)


class HashEmbedder:
    """确定性伪嵌入：字符 bigram → 固定维度哈希桶，L2 归一化。

    只用于基准测试的可复现性，不代表真实语义质量；
    召回指标用于回归对比，不作为对外效果声明。
    """

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        cleaned = "".join(text.split()).lower()
        for index in range(max(1, len(cleaned) - 1)):
            gram = cleaned[index:index + 2] or cleaned
            digest = hashlib.md5(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def build_corpus(session: Session, chunks: int, dim: int, seed: int = 7) -> list[dict]:
    """写入合成文档与分块，返回每条查询对应种子（查询文本 + 期望命中的 doc 标题）。"""
    from app.models import DocChunk, Document

    rng = random.Random(seed)
    embedder = HashEmbedder(dim)
    cases: list[dict] = []
    docs_per_chunk = 10
    doc_total = max(1, chunks // docs_per_chunk)
    for doc_index in range(doc_total):
        fault = FAULTS[doc_index % len(FAULTS)]
        measure = MEASURES[doc_index % len(MEASURES)]
        model = DEVICE_MODELS[doc_index % len(DEVICE_MODELS)]
        marker = f"批次{doc_index}号"
        title = f"{model}-{fault}-手册-{doc_index}"
        doc = Document(title=title, status="approved", device_model=model)
        session.add(doc)
        session.flush()
        for page in range(docs_per_chunk):
            content = (
                f"{fault}：检查第{page + 1}项，{measure}。"
                f"适用于设备型号 {model}，记录编号 {doc_index}-{page}。"
            )
            session.add(DocChunk(
                doc_id=doc.id,
                page=page,
                content=content,
                embedding=embedder.embed_one(content),
            ))
        cases.append({
            "query": f"{fault} {marker} 怎么处理",
            "device_model": model,
            "expected_doc_title": title,
        })
    session.commit()
    rng.shuffle(cases)
    return cases


def run_bench(chunks: int, queries: int, top_k: int, dim: int) -> dict:
    from app.config import settings
    import app.rag.retriever as retriever

    settings.embedding_dim = dim
    settings.retrieval_mode = "hybrid"
    settings.vector_backend = "python"
    settings.parent_child_enabled = False
    settings.graph_rag_enabled = False
    settings.query_rewrite_enabled = False

    embedder = HashEmbedder(dim)
    retriever.get_embedder = lambda: embedder  # type: ignore[assignment]

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'bench.db'}", future=True)
        from app.db import Base
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            cases = build_corpus(session, chunks, dim)
            cases = (cases * ((queries // len(cases)) + 1))[:queries]

            # 预热：按设备型号各建一次索引，避免把首次建索引算进稳态延迟。
            for model in {case["device_model"] for case in cases}:
                retriever.retrieve(session, "预热检索", device_model=model, top_k=top_k)

            latencies: list[float] = []
            hits = 0
            for case in cases:
                started = time.perf_counter()
                results = retriever.retrieve(
                    session, case["query"], device_model=case["device_model"], top_k=top_k,
                )
                latencies.append((time.perf_counter() - started) * 1000)
                if any(item["doc_title"] == case["expected_doc_title"] for item in results):
                    hits += 1
        engine.dispose()

    latencies.sort()
    return {
        "chunks": chunks,
        "queries": len(cases),
        "top_k": top_k,
        "embedding_dim": dim,
        "retrieval_mode": "hybrid",
        "latency_ms_p50": round(statistics.median(latencies), 2),
        "latency_ms_p95": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 2),
        "latency_ms_max": round(latencies[-1], 2),
        "recall_at_k": round(hits / len(cases), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="合成语料检索基准")
    parser.add_argument("--chunks", type=int, default=10000)
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--embedding-dim", type=int, default=512)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()

    summary = run_bench(args.chunks, args.queries, args.top_k, args.embedding_dim)
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.output / f"bench-{stamp}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.fail_on_threshold:
        thresholds = load_thresholds()
        spec = thresholds.get("bench")
        if spec:
            ok, failures = check_metrics(summary, spec)
            for failure in failures:
                print(f"[threshold] {failure}")
            return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
