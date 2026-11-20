\set ON_ERROR_STOP on

\if :{?embedding_dim}
\else
\set embedding_dim 512
\endif

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT to_regclass('public.doc_chunks') IS NOT NULL AS chunks_exists \gset

\if :chunks_exists
SELECT
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'doc_chunks'
          AND column_name = 'embedding'
          AND udt_name IN ('json', 'jsonb')
    ) AS embedding_is_json,
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'doc_chunks'
          AND column_name = 'embedding'
          AND udt_name = 'vector'
    ) AS embedding_is_vector,
    EXISTS (
        SELECT 1
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relname = 'doc_chunks'
          AND a.attname = 'embedding'
          AND format_type(a.atttypid, a.atttypmod) = format('vector(%s)', :embedding_dim)
    ) AS vector_dimension_matches \gset

\if :embedding_is_json
ALTER TABLE doc_chunks
    ALTER COLUMN embedding TYPE vector(:embedding_dim)
    USING CASE
        WHEN embedding IS NULL THEN NULL
        ELSE embedding::text::vector
    END;
\elif :embedding_is_vector
\if :vector_dimension_matches
\echo 'doc_chunks.embedding vector dimension matches embedding_dim'
\else
\echo 'Existing vector dimension does not match embedding_dim; re-embedding is required before migration'
\quit 4
\endif
\else
\echo 'Unsupported or missing doc_chunks.embedding column'
\quit 3
\endif

CREATE INDEX IF NOT EXISTS ix_doc_chunks_embedding_hnsw
    ON doc_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_doc_chunks_content_trgm
    ON doc_chunks USING gin (content gin_trgm_ops);
\else
\echo 'doc_chunks does not exist; application startup will create the vector column'
\endif
