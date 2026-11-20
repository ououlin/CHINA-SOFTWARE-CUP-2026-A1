"""检索器：向量召回 + 混合重排（增强 G8）+ 设备型号结构化过滤。

流程：先用向量余弦召回较多候选（top_k×3），再做二次重排——
融合「语义相似度」与「字面词项重叠（中文 bigram + 英文/数字词）」重新打分，
弥补纯向量在专有名词/型号上的不足，提升引用准确率。纯 Python、零依赖。

开发期(SQLite)：把候选分块的向量取到内存算余弦。
生产(PostgreSQL)：pgvector 向量召回 + pg_trgm 字面召回，再以 RRF 融合排序。

优化：先在数据库层面按 device_model 过滤文档，减少全表扫描开销。
"""
import heapq
import math
import re
import time
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..embedding import get_embedder
from ..metrics import observe
from ..models import DocChunk, Document

try:  # 可选加速器：有 numpy 时向量打分为矩阵乘，无则退回纯 Python（LoongArch 生产路径不依赖 numpy）
    import numpy as _np
except ImportError:  # pragma: no cover - 取决于运行环境
    _np = None

# 重排融合权重与召回倍数
_VEC_WEIGHT = 0.7
_LEX_WEIGHT = 0.3
_RECALL_MULT = 3
_RECALL_MIN = 12

# 语料索引缓存：键为 (引擎实例, 设备型号)，用 (行数, 最大 id) 做版本号失效；
# TTL 兜底处理「原地更新内容但行数不变」的场景。
_INDEX_CACHE: dict[tuple, dict] = {}
_INDEX_TTL_SECONDS = 120.0
_CORPUS_VERSION_SQL = text(
    "SELECT count(*) AS total, coalesce(max(id), 0) AS latest FROM doc_chunks"
)

_CJK_RE = re.compile(r"[一-鿿]")
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def normalize_model(value: str) -> str:
    """设备型号标准化：忽略空格、横线、下划线与大小写差异。"""
    return re.sub(r"[\s_\-]+", "", value or "").lower()


def _terms(text: str) -> set:
    """词项集合：中文相邻字 bigram + 英文/数字词（小写）。"""
    chars = _CJK_RE.findall(text)
    terms = set(a + b for a, b in zip(chars, chars[1:]))
    terms |= set(w.lower() for w in _WORD_RE.findall(text))
    return terms


def _lexical(q_terms: set, content: str) -> float:
    """字面重叠：命中的查询词项占比（0~1）。"""
    if not q_terms:
        return 0.0
    inter = len(q_terms & _terms(content))
    return inter / len(q_terms)


def _overlap_ratio(q_terms: set, chunk_terms: set) -> float:
    """同 `_lexical`，但复用预先算好的分块词项集合，避免每次查询重复分词。"""
    if not q_terms:
        return 0.0
    return len(q_terms & chunk_terms) / len(q_terms)


def invalidate_retrieval_cache() -> None:
    """清空语料索引缓存；写入/审核后如发现检索滞后可直接调用。"""
    _INDEX_CACHE.clear()


def _corpus_version(db: Session) -> tuple[int, int]:
    row = db.execute(_CORPUS_VERSION_SQL).one()
    return int(row[0]), int(row[1])


def _build_index(db: Session, device_model: Optional[str]) -> dict:
    """把分块与其向量整理成可复用的内存索引（含词项集合与归一化向量矩阵）。"""
    entries = []
    for chunk, doc in _load_filtered_chunks(db, device_model):
        entries.append({
            "chunk_id": chunk.id,
            "doc_id": doc.id,
            "page": chunk.page,
            "content": chunk.content,
            "doc_title": doc.title,
            "device_model": doc.device_model,
            "vector": chunk.embedding or [],
            "terms": _terms(chunk.content),
        })
    index: dict = {"entries": entries, "matrix": None}
    if _np is not None and entries:
        dim = settings.embedding_dim
        matrix = _np.zeros((len(entries), dim), dtype=_np.float32)
        usable = 0
        for row, entry in enumerate(entries):
            vector = entry["vector"]
            if vector and len(vector) == dim:
                matrix[row] = vector
                usable += 1
        if usable:
            norms = _np.linalg.norm(matrix, axis=1)
            norms[norms == 0] = 1.0
            index["matrix"] = matrix / norms[:, None]
    return index


def _load_index(db: Session, device_model: Optional[str]) -> dict:
    """取语料索引：命中缓存时只花一次 count/max(id) 的版本查询。"""
    bind = db.get_bind()
    key = (id(bind), normalize_model(device_model or ""))
    version = _corpus_version(db)
    cached = _INDEX_CACHE.get(key)
    if (
        cached is not None
        and cached["version"] == version
        and time.monotonic() - cached["loaded_at"] < _INDEX_TTL_SECONDS
    ):
        return cached
    index = _build_index(db, device_model)
    index["version"] = version
    index["loaded_at"] = time.monotonic()
    _INDEX_CACHE[key] = index
    return index


def _top_indices(scores: List[float], limit: int) -> List[int]:
    if limit <= 0 or not scores:
        return []
    if limit >= len(scores):
        return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return heapq.nlargest(limit, range(len(scores)), key=lambda i: scores[i])


def _parent_contexts(db: Session, items: List[tuple], window: int) -> dict:
    """批量取父上下文：一次查询取回相关文档的全部块，避免每条结果一次查询（N+1）。"""
    doc_ids = {item[1] for item in items}
    if not doc_ids:
        return {}
    rows = db.execute(
        select(DocChunk.id, DocChunk.doc_id, DocChunk.content)
        .where(DocChunk.doc_id.in_(doc_ids))
        .order_by(DocChunk.doc_id, DocChunk.page, DocChunk.id)
    ).all()
    grouped: dict = {}
    for chunk_id, doc_id, content in rows:
        grouped.setdefault(doc_id, []).append((chunk_id, content))
    contexts = {}
    for chunk_id, doc_id in items:
        siblings = grouped.get(doc_id) or []
        ids = [item[0] for item in siblings]
        if chunk_id not in ids:
            continue
        position = ids.index(chunk_id)
        low = max(0, position - window)
        high = min(len(siblings), position + window + 1)
        if high - low > 1:
            contexts[chunk_id] = "\n".join(item[1] for item in siblings[low:high])
    return contexts


def _parent_content(db: Session, doc_id: int, chunk_id: int, window: int) -> Optional[str]:
    """父子分块：取同文档相邻 window 个块拼成父上下文（召回子块、喂模型父块）。"""
    sibs = db.execute(
        select(DocChunk.id, DocChunk.content)
        .where(DocChunk.doc_id == doc_id)
        .order_by(DocChunk.page, DocChunk.id)
    ).all()
    ids = [s[0] for s in sibs]
    if chunk_id not in ids:
        return None
    i = ids.index(chunk_id)
    lo, hi = max(0, i - window), min(len(sibs), i + window + 1)
    if hi - lo <= 1:
        return None  # 文档仅一块，无父上下文可扩展
    return "\n".join(s[1] for s in sibs[lo:hi])


def _load_filtered_chunks(db: Session, device_model: Optional[str]) -> list:
    """先在数据库层面过滤文档型号，再加载分块数据，减少不必要的内存占用。"""
    stmt = select(DocChunk, Document).join(Document, DocChunk.doc_id == Document.id)
    stmt = stmt.where(Document.status == "approved")

    if device_model:
        model_norm = normalize_model(device_model)
        all_docs = db.execute(
            select(Document.id, Document.device_model)
            .where(Document.status == "approved")
        ).all()
        exact_doc_ids = [
            doc_id for doc_id, dm in all_docs
            if normalize_model(dm or "") == model_norm
        ]
        matched_doc_ids = exact_doc_ids or [
            doc_id for doc_id, dm in all_docs
            if model_norm and model_norm in normalize_model(dm or "")
        ]
        if matched_doc_ids:
            stmt = stmt.where(DocChunk.doc_id.in_(matched_doc_ids))
        # 型号完全未命中时保留全库回退，避免返回空答案。

    return db.execute(stmt).all()


def _vector_literal(vector: List[float]) -> str:
    if len(vector) != settings.embedding_dim:
        raise ValueError(
            f"Embedding 维度不匹配：期望 {settings.embedding_dim}，实际 {len(vector)}"
        )
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


def _retrieve_postgres(
    db: Session,
    query: str,
    qvec: List[float],
    device_model: Optional[str],
    top_k: int,
) -> List[dict]:
    """PostgreSQL production path: pgvector + pg_trgm recall fused by RRF."""
    candidate_k = max(settings.hybrid_candidate_k, top_k * _RECALL_MULT)
    # 生产检索走 HNSW：按配置调 ef_search（会话级），在召回与延迟之间取舍。
    if settings.pgvector_ef_search and settings.pgvector_ef_search > 0:
        try:
            db.execute(
                text("SELECT set_config('hnsw.ef_search', :value, false)"),
                {"value": str(int(settings.pgvector_ef_search))},
            )
        except Exception:  # 扩展版本不支持该参数时保持默认值
            pass
    use_vector = 0.0 if settings.retrieval_mode == "lexical" else 1.0
    use_lexical = 0.0 if settings.retrieval_mode == "vector" else 1.0
    sql = text("""
        WITH model_state AS MATERIALIZED (
            SELECT
              EXISTS (
                SELECT 1 FROM documents d
                WHERE d.status = 'approved'
                  AND regexp_replace(lower(coalesce(d.device_model, '')), '[[:space:]_-]+', '', 'g')
                      = :model_norm
              ) AS has_exact_match,
              EXISTS (
                SELECT 1 FROM documents d
                WHERE d.status = 'approved'
                  AND :model_norm <> ''
                  AND strpos(
                        regexp_replace(lower(coalesce(d.device_model, '')), '[[:space:]_-]+', '', 'g'),
                        :model_norm
                      ) > 0
              ) AS has_partial_match
        ),
        eligible AS MATERIALIZED (
            SELECT
                c.id AS chunk_id, c.doc_id, c.page, c.content, c.embedding,
                d.title AS doc_title, d.device_model
            FROM doc_chunks c
            JOIN documents d ON d.id = c.doc_id
            CROSS JOIN model_state ms
            WHERE d.status = 'approved'
              AND (
                :model_norm = '' OR
                (
                  ms.has_exact_match AND
                  regexp_replace(lower(coalesce(d.device_model, '')), '[[:space:]_-]+', '', 'g')
                      = :model_norm
                ) OR
                (
                  NOT ms.has_exact_match AND ms.has_partial_match AND
                  strpos(
                    regexp_replace(lower(coalesce(d.device_model, '')), '[[:space:]_-]+', '', 'g'),
                    :model_norm
                  ) > 0
                ) OR
                (NOT ms.has_exact_match AND NOT ms.has_partial_match)
              )
        ),
        vector_ranked AS (
            SELECT
                chunk_id,
                1 - (embedding <=> CAST(:query_vector AS vector)) AS vec_score,
                row_number() OVER (
                    ORDER BY embedding <=> CAST(:query_vector AS vector)
                ) AS rank_no
            FROM eligible
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:query_vector AS vector)
            LIMIT :candidate_k
        ),
        lexical_ranked AS (
            SELECT
                chunk_id,
                similarity(content, :query) AS lex_score,
                row_number() OVER (
                    ORDER BY similarity(content, :query) DESC
                ) AS rank_no
            FROM eligible
            ORDER BY similarity(content, :query) DESC
            LIMIT :candidate_k
        ),
        fused AS (
            SELECT
                chunk_id,
                max(vec_score) AS vec_score,
                max(lex_score) AS lex_score,
                sum(rrf_score) AS rrf_score
            FROM (
                SELECT chunk_id, vec_score, NULL::double precision AS lex_score,
                       CAST(:use_vector AS double precision)
                           / (CAST(:rrf_k AS double precision) + rank_no) AS rrf_score
                FROM vector_ranked
                UNION ALL
                SELECT chunk_id, NULL::double precision AS vec_score, lex_score,
                       CAST(:use_lexical AS double precision)
                           / (CAST(:rrf_k AS double precision) + rank_no) AS rrf_score
                FROM lexical_ranked
            ) ranked
            GROUP BY chunk_id
        )
        SELECT
            e.chunk_id, e.doc_id, e.doc_title, e.device_model, e.page, e.content,
            coalesce(f.vec_score, 0) AS vec_score,
            coalesce(f.lex_score, 0) AS lex_score,
            f.rrf_score
        FROM fused f
        JOIN eligible e ON e.chunk_id = f.chunk_id
        ORDER BY f.rrf_score DESC, f.vec_score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "query": query,
        "query_vector": _vector_literal(qvec),
        "model_norm": normalize_model(device_model or ""),
        "candidate_k": candidate_k,
        "rrf_k": float(settings.hybrid_rrf_k),
        "top_k": top_k,
        "use_vector": use_vector,
        "use_lexical": use_lexical,
    }).mappings().all()

    results = []
    for row in rows:
        vec = max(-1.0, min(1.0, float(row["vec_score"] or 0)))
        lex = max(0.0, min(1.0, float(row["lex_score"] or 0)))
        item = {
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "doc_title": row["doc_title"],
            "device_model": row["device_model"],
            "page": row["page"],
            "content": row["content"],
            "score": round(
                vec if settings.retrieval_mode == "vector"
                else lex if settings.retrieval_mode == "lexical"
                else vec * _VEC_WEIGHT + lex * _LEX_WEIGHT,
                4,
            ),
            "vec_score": round(vec, 4),
            "lex_score": round(lex, 4),
            "rrf_score": round(float(row["rrf_score"]), 6),
            "retrieval_method": f"pgvector_trgm_rrf:{settings.retrieval_mode}",
        }
        if settings.parent_child_enabled:
            parent = _parent_content(
                db, row["doc_id"], row["chunk_id"], settings.parent_window,
            )
            if parent and parent != row["content"]:
                item["parent_content"] = parent
        results.append(item)
    return results


def retrieve(
    db: Session,
    query: str,
    device_model: Optional[str] = None,
    top_k: Optional[int] = None,
) -> List[dict]:
    _t0 = time.perf_counter()
    top_k = top_k or settings.retrieve_top_k
    candidate_k = max(settings.hybrid_candidate_k, top_k * _RECALL_MULT, _RECALL_MIN)
    qvec = (
        [0.0] * settings.embedding_dim
        if settings.retrieval_mode == "lexical"
        else get_embedder().embed_one(query)
    )

    dialect = db.get_bind().dialect.name
    use_postgres = (
        dialect == "postgresql"
        and settings.vector_backend in ("auto", "pgvector")
    )
    if use_postgres:
        results = _retrieve_postgres(db, query, qvec, device_model, top_k)
        observe("rag_retrieve", time.perf_counter() - _t0)
        return results

    # SQLite/Python 回退：取语料索引（带版本缓存），向量与字面分别召回候选，再用 RRF 合并。
    load_started = time.perf_counter()
    index = _load_index(db, device_model)
    observe("rag_retrieve_corpus", time.perf_counter() - load_started)

    entries = index["entries"]
    if not entries:
        observe("rag_retrieve", time.perf_counter() - _t0)
        return []

    score_started = time.perf_counter()
    q_terms = _terms(query)
    matrix = index["matrix"]
    if _np is not None and matrix is not None:
        query_vec = _np.asarray(qvec, dtype=_np.float32)
        norm = float(_np.linalg.norm(query_vec)) or 1.0
        vec_scores = (matrix @ (query_vec / norm)).tolist()
    else:
        vec_scores = [_cosine(qvec, entry["vector"]) for entry in entries]
    lex_scores = [_overlap_ratio(q_terms, entry["terms"]) for entry in entries]
    observe("rag_retrieve_score", time.perf_counter() - score_started)

    fused: dict = {}
    if settings.retrieval_mode != "lexical":
        for rank, position in enumerate(_top_indices(vec_scores, candidate_k), start=1):
            fused[position] = [1.0 / (settings.hybrid_rrf_k + rank)]
    if settings.retrieval_mode != "vector":
        for rank, position in enumerate(_top_indices(lex_scores, candidate_k), start=1):
            item = fused.setdefault(position, [0.0])
            item[0] += 1.0 / (settings.hybrid_rrf_k + rank)
    ranked = sorted(
        fused,
        key=lambda position: (fused[position][0], vec_scores[position], lex_scores[position]),
        reverse=True,
    )[:top_k]

    parents: dict = {}
    if settings.parent_child_enabled and ranked:
        # 一次查询取回全部父上下文，替代逐条查询（原实现为 N+1）。
        parents = _parent_contexts(
            db,
            [(entries[position]["chunk_id"], entries[position]["doc_id"]) for position in ranked],
            settings.parent_window,
        )

    results = []
    for position in ranked:
        entry = entries[position]
        rrf_score = fused[position][0]
        vec = vec_scores[position]
        lex = lex_scores[position]
        final = (
            vec if settings.retrieval_mode == "vector"
            else lex if settings.retrieval_mode == "lexical"
            else vec * _VEC_WEIGHT + lex * _LEX_WEIGHT
        )
        item = {
            "chunk_id": entry["chunk_id"],
            "doc_id": entry["doc_id"],
            "doc_title": entry["doc_title"],
            "device_model": entry["device_model"],
            "page": entry["page"],
            "content": entry["content"],        # 精确子块，用于引用展示
            "score": round(float(final), 4),
            "vec_score": round(float(vec), 4),
            "lex_score": round(float(lex), 4),
            "rrf_score": round(float(rrf_score), 6),
            "retrieval_method": f"python_rrf:{settings.retrieval_mode}",
        }
        parent = parents.get(entry["chunk_id"])
        if parent and parent != entry["content"]:
            item["parent_content"] = parent  # 父块上下文，喂模型用
        results.append(item)

    observe("rag_retrieve", time.perf_counter() - _t0)
    return results
