-- Локальная схема JARVIS для PostgreSQL 17 + pgvector 0.8+.
-- Применяется в БД `jarvis_local` (отдельная от `expertise_ntd`).
-- Идемпотентна — можно гонять повторно.
--
-- Аналог Supabase setup_supabase.sql, но без RLS / service_role —
-- доступ к локальному PG ограничен ОС. Сохранены все сигнатуры
-- RPC (`match_jarvis_memory`, `get_jarvis_stats`) для совместимости.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── Память JARVIS (идеи, заметки, задачи, отчёты) ────────────────────────────
CREATE TABLE IF NOT EXISTS jarvis_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content         TEXT NOT NULL,
    content_type    TEXT NOT NULL CHECK (content_type IN
                      ('idea','task','note','query','decision','context','agent_report','digest')),
    summary         TEXT,
    tags            TEXT[] DEFAULT '{}',
    embedding       vector(1536),
    source          TEXT DEFAULT 'user',
    priority        TEXT DEFAULT 'medium' CHECK (priority IN ('critical','high','medium','low')),
    status          TEXT DEFAULT 'active'  CHECK (status   IN ('active','archived','completed','dismissed')),
    related_project TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Материализованная FTS-колонка для гибридного поиска
-- (русская морфология; STORED — обновляется автоматом при UPDATE content).
ALTER TABLE jarvis_memory
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('russian', coalesce(content,'') || ' ' || coalesce(summary,''))
  ) STORED;

CREATE INDEX IF NOT EXISTS jarvis_memory_embedding_hnsw
  ON jarvis_memory USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS jarvis_memory_fts_gin   ON jarvis_memory USING GIN (fts);
CREATE INDEX IF NOT EXISTS jarvis_memory_tags_gin  ON jarvis_memory USING GIN (tags);
CREATE INDEX IF NOT EXISTS jarvis_memory_meta_gin  ON jarvis_memory USING GIN (metadata);
CREATE INDEX IF NOT EXISTS jarvis_memory_type      ON jarvis_memory (content_type);
CREATE INDEX IF NOT EXISTS jarvis_memory_status    ON jarvis_memory (status);
CREATE INDEX IF NOT EXISTS jarvis_memory_created   ON jarvis_memory (created_at DESC);
CREATE INDEX IF NOT EXISTS jarvis_memory_project
  ON jarvis_memory (related_project) WHERE related_project IS NOT NULL;

-- ─── Контексты проектов ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jarvis_projects (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    description   TEXT,
    status        TEXT DEFAULT 'active' CHECK (status IN ('active','paused','completed','archived')),
    agents        TEXT[] DEFAULT '{}',
    key_decisions JSONB  DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jarvis_projects_status ON jarvis_projects (status);

-- ─── Аудит-лог действий агентов ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jarvis_agent_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    input_data  JSONB,
    output_data JSONB,
    status      TEXT CHECK (status IN ('success','error','pending','timeout')),
    duration_ms INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jarvis_agent_logs_agent  ON jarvis_agent_logs (agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS jarvis_agent_logs_status ON jarvis_agent_logs (status);

-- ─── Триггер на updated_at ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION jarvis_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS jarvis_memory_update_ts   ON jarvis_memory;
DROP TRIGGER IF EXISTS jarvis_projects_update_ts ON jarvis_projects;

CREATE TRIGGER jarvis_memory_update_ts
  BEFORE UPDATE ON jarvis_memory
  FOR EACH ROW EXECUTE FUNCTION jarvis_touch_updated_at();

CREATE TRIGGER jarvis_projects_update_ts
  BEFORE UPDATE ON jarvis_projects
  FOR EACH ROW EXECUTE FUNCTION jarvis_touch_updated_at();

-- ─── Поисковые функции (совместимы по сигнатуре с Supabase RPC) ───────────────

-- 1. Чисто векторный поиск — сигнатура идентична Supabase match_jarvis_memory.
CREATE OR REPLACE FUNCTION match_jarvis_memory(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count     int   DEFAULT 10,
    filter_type     text  DEFAULT NULL,
    filter_status   text  DEFAULT 'active'
) RETURNS TABLE (
    id              UUID,
    content         TEXT,
    content_type    TEXT,
    summary         TEXT,
    tags            TEXT[],
    metadata        JSONB,
    related_project TEXT,
    similarity      float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        jm.id,
        jm.content,
        jm.content_type,
        jm.summary,
        jm.tags,
        jm.metadata,
        jm.related_project,
        1 - (jm.embedding <=> query_embedding) AS similarity
    FROM jarvis_memory jm
    WHERE jm.embedding IS NOT NULL
      AND 1 - (jm.embedding <=> query_embedding) > match_threshold
      AND (filter_type   IS NULL OR jm.content_type = filter_type)
      AND (filter_status IS NULL OR jm.status       = filter_status)
    ORDER BY jm.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- 2. Статистика по типам контента — совместима с Supabase get_jarvis_stats.
CREATE OR REPLACE FUNCTION get_jarvis_stats()
RETURNS TABLE (
    content_type TEXT,
    count        BIGINT,
    latest       TIMESTAMPTZ
)
LANGUAGE sql STABLE
AS $$
    SELECT
        jm.content_type,
        COUNT(*)            AS count,
        MAX(jm.created_at)  AS latest
    FROM jarvis_memory jm
    WHERE jm.status = 'active'
    GROUP BY jm.content_type
    ORDER BY count DESC;
$$;

-- 3. Гибридный поиск (BM25 + cosine, RRF-объединение). Новая RPC —
-- нет аналога в Supabase, но полезна локально для лучшей релевантности.
-- filter_type / filter_status — те же фильтры, что у match_jarvis_memory.
CREATE OR REPLACE FUNCTION hybrid_search_jarvis_memory(
    query_text      text,
    query_embedding vector(1536),
    match_count     int  DEFAULT 8,
    candidates      int  DEFAULT 40,
    k_rrf           int  DEFAULT 60,
    filter_type     text DEFAULT NULL,
    filter_status   text DEFAULT 'active'
) RETURNS TABLE (
    id              UUID,
    content         TEXT,
    content_type    TEXT,
    summary         TEXT,
    tags            TEXT[],
    metadata        JSONB,
    related_project TEXT,
    vec_score       float,
    fts_score       float,
    rrf_score       float
)
LANGUAGE sql STABLE
AS $$
  WITH filtered AS (
    SELECT jm.*
    FROM jarvis_memory jm
    WHERE jm.embedding IS NOT NULL
      AND (filter_type   IS NULL OR jm.content_type = filter_type)
      AND (filter_status IS NULL OR jm.status       = filter_status)
  ),
  vec AS (
    SELECT id, 1 - (embedding <=> query_embedding) AS score,
           ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) AS rnk
    FROM filtered
    ORDER BY embedding <=> query_embedding
    LIMIT candidates
  ),
  fts AS (
    SELECT id, ts_rank(fts, plainto_tsquery('russian', query_text)) AS score,
           ROW_NUMBER() OVER (
             ORDER BY ts_rank(fts, plainto_tsquery('russian', query_text)) DESC
           ) AS rnk
    FROM filtered
    WHERE fts @@ plainto_tsquery('russian', query_text)
    LIMIT candidates
  ),
  merged AS (
    SELECT
      COALESCE(v.id, t.id) AS id,
      COALESCE(v.score, 0) AS vec_score,
      COALESCE(t.score, 0) AS fts_score,
      COALESCE(1.0 / (k_rrf + v.rnk), 0) + COALESCE(1.0 / (k_rrf + t.rnk), 0) AS rrf_score
    FROM vec v
    FULL OUTER JOIN fts t USING (id)
  )
  SELECT
    f.id, f.content, f.content_type, f.summary, f.tags, f.metadata, f.related_project,
    m.vec_score, m.fts_score, m.rrf_score
  FROM merged m
  JOIN filtered f USING (id)
  ORDER BY m.rrf_score DESC
  LIMIT match_count;
$$;

-- ─── Представление для аналитики ──────────────────────────────────────────────
CREATE OR REPLACE VIEW jarvis_daily_activity AS
SELECT
    DATE(created_at) AS date,
    agent_id,
    COUNT(*)                                              AS total_actions,
    COUNT(*) FILTER (WHERE status = 'success')            AS successful,
    COUNT(*) FILTER (WHERE status = 'error')              AS failed,
    AVG(duration_ms)::int                                 AS avg_duration_ms
FROM jarvis_agent_logs
GROUP BY DATE(created_at), agent_id
ORDER BY date DESC;
