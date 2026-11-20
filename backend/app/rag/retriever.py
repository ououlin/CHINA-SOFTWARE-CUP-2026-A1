"""检索器：向量召回 + 混合重排（增强 G8）+ 设备型号结构化过滤。

流程：先用向量余弦召回较多候选（top_k×3），再做二次重排——
融合「语义相似度」与「字面词项重叠（中文 bigram + 英文/数字词）」重新打分，
弥补纯向量在专有名词/型号上的不足，提升引用准确率。纯 Python、零依赖。

开发期(SQLite)：把候选分块的向量取到内存算余弦。
生产(PostgreSQL)：pgvector 向量召回 + pg_trgm 字面召回，再以 RRF 融合排序。

优化：先在数据库层面按 device_model 过滤文档，减少全表扫描开销。
"""
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

# 重排融合权重与召回倍数
_VEC_WEIGHT = 0.7
_LEX_WEIGHT = 0.3
_RECALL_MULT = 3
_RECALL_MIN = 12

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
    use_vector = 0.0 if settings.retrieval_mode == "lexical" else 1.0
    use_lexical = 0.0 if settings.retrieval_mode == "vector" else 1.0
    sql = text("""
        WITH model_state AS (
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
        eligible AS (
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

    # 优化：先在数据库层面过滤，避免全表扫描
    rows = _load_filtered_chunks(db, device_model)

    # SQLite/Python 回退：向量与字面分别召回候选，再用 RRF 合并。
    q_terms = _terms(query)
    scored = []
    for chunk, doc in rows:
        # 混合/字面模式仍须保留尚未生成向量的文本分块。
        if not chunk.embedding and settings.retrieval_mode == "vector":
            continue
        vec = _cosine(qvec, chunk.embedding or [])
        lex = _lexical(q_terms, chunk.content)
        scored.append((vec, lex, chunk, doc))

    vector_top = sorted(scored, key=lambda x: x[0], reverse=True)[:candidate_k]
    lexical_top = sorted(scored, key=lambda x: x[1], reverse=True)[:candidate_k]
    fused = {}
    if settings.retrieval_mode != "lexical":
        for rank, (vec, lex, chunk, doc) in enumerate(vector_top, start=1):
            fused[chunk.id] = [1.0 / (settings.hybrid_rrf_k + rank), vec, lex, chunk, doc]
    if settings.retrieval_mode != "vector":
        for rank, (vec, lex, chunk, doc) in enumerate(lexical_top, start=1):
            item = fused.setdefault(chunk.id, [0.0, vec, lex, chunk, doc])
            item[0] += 1.0 / (settings.hybrid_rrf_k + rank)
    candidates = sorted(fused.values(), key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for rrf_score, vec, lex, chunk, doc in candidates[:top_k]:
        final = (
            vec if settings.retrieval_mode == "vector"
            else lex if settings.retrieval_mode == "lexical"
            else vec * _VEC_WEIGHT + lex * _LEX_WEIGHT
        )
        item = {
            "chunk_id": chunk.id,
            "doc_id": doc.id,
            "doc_title": doc.title,
            "device_model": doc.device_model,
            "page": chunk.page,
            "content": chunk.content,        # 精确子块，用于引用展示
            "score": round(float(final), 4),
            "vec_score": round(float(vec), 4),
            "lex_score": round(float(lex), 4),
            "rrf_score": round(float(rrf_score), 6),
            "retrieval_method": f"python_rrf:{settings.retrieval_mode}",
        }
        if settings.parent_child_enabled:
            pc = _parent_content(db, doc.id, chunk.id, settings.parent_window)
            if pc and pc != chunk.content:
                item["parent_content"] = pc  # 父块上下文，喂模型用
        results.append(item)

    observe("rag_retrieve", time.perf_counter() - _t0)
    return results
