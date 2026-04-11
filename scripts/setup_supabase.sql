-- ================================================================
-- JARVIS — Supabase Setup
-- ================================================================
-- Версия: 1.0.0
-- Дата: 2026-04-10
--
-- Адаптировано из RAG-Consultant/supabase-setup.sql
-- 3 таблицы: jarvis_memory, jarvis_projects, jarvis_agent_logs
-- ================================================================

-- 1. Включить расширение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ================================================================
-- 2. Таблица памяти JARVIS (основная)
-- ================================================================
-- Хранит всё: идеи, заметки, задачи, контексты, отчёты агентов
-- Идеи хранятся через content_type = 'idea' + scoring в metadata

CREATE TABLE IF NOT EXISTS jarvis_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type IN ('idea', 'task', 'note', 'query', 'decision', 'context', 'agent_report', 'digest')),
    summary TEXT,
    tags TEXT[] DEFAULT '{}',
    embedding VECTOR(1536),                    -- OpenAI text-embedding-3-small
    source TEXT DEFAULT 'user',                -- user, telegram, agent:<id>, auto, seed
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived', 'completed', 'dismissed')),
    related_project TEXT,
    metadata JSONB DEFAULT '{}',               -- Для идей: {feasibility_score, impact_score, evaluation_notes}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE jarvis_memory IS 'Второй мозг JARVIS — хранит все записи с векторными эмбеддингами для семантического поиска';
COMMENT ON COLUMN jarvis_memory.content_type IS 'Тип записи: idea, task, note, query, decision, context, agent_report, digest';
COMMENT ON COLUMN jarvis_memory.metadata IS 'Для идей: feasibility_score (1-10), impact_score (1-10), evaluation_notes';

-- ================================================================
-- 3. Таблица проектов
-- ================================================================

CREATE TABLE IF NOT EXISTS jarvis_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    agents TEXT[] DEFAULT '{}',
    key_decisions JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE jarvis_projects IS 'Контексты проектов JARVIS — какие агенты задействованы, ключевые решения';

-- ================================================================
-- 4. Таблица логов агентов
-- ================================================================

CREATE TABLE IF NOT EXISTS jarvis_agent_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    status TEXT CHECK (status IN ('success', 'error', 'pending', 'timeout')),
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE jarvis_agent_logs IS 'Аудит-лог всех действий агентов JARVIS';

-- ================================================================
-- 5. Индексы
-- ================================================================

-- HNSW индекс для быстрого векторного поиска (косинусная схожесть)
CREATE INDEX IF NOT EXISTS idx_jarvis_memory_embedding_hnsw
    ON jarvis_memory USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN индекс для поиска по тегам
CREATE INDEX IF NOT EXISTS idx_jarvis_memory_tags
    ON jarvis_memory USING gin (tags);

-- B-tree индексы для фильтрации
CREATE INDEX IF NOT EXISTS idx_jarvis_memory_type
    ON jarvis_memory (content_type);

CREATE INDEX IF NOT EXISTS idx_jarvis_memory_status
    ON jarvis_memory (status);

CREATE INDEX IF NOT EXISTS idx_jarvis_memory_created
    ON jarvis_memory (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jarvis_memory_project
    ON jarvis_memory (related_project)
    WHERE related_project IS NOT NULL;

-- GIN индекс для metadata (оценки идей и т.п.)
CREATE INDEX IF NOT EXISTS idx_jarvis_memory_metadata
    ON jarvis_memory USING gin (metadata);

-- Индексы для логов агентов
CREATE INDEX IF NOT EXISTS idx_agent_logs_agent
    ON jarvis_agent_logs (agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_logs_status
    ON jarvis_agent_logs (status);

-- Индексы для проектов
CREATE INDEX IF NOT EXISTS idx_projects_status
    ON jarvis_projects (status);

-- ================================================================
-- 6. RPC функция для семантического поиска
-- ================================================================
-- Адаптировано из RAG-Consultant match_documents

CREATE OR REPLACE FUNCTION match_jarvis_memory(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10,
    filter_type TEXT DEFAULT NULL,
    filter_status TEXT DEFAULT 'active'
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    content_type TEXT,
    summary TEXT,
    tags TEXT[],
    metadata JSONB,
    related_project TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
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
    WHERE 1 - (jm.embedding <=> query_embedding) > match_threshold
        AND (filter_type IS NULL OR jm.content_type = filter_type)
        AND (filter_status IS NULL OR jm.status = filter_status)
    ORDER BY jm.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_jarvis_memory IS 'Семантический поиск по памяти JARVIS с фильтрами по типу и статусу';

-- ================================================================
-- 7. RPC функция для статистики памяти
-- ================================================================

CREATE OR REPLACE FUNCTION get_jarvis_stats()
RETURNS TABLE (
    content_type TEXT,
    count BIGINT,
    latest TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        jm.content_type,
        COUNT(*) AS count,
        MAX(jm.created_at) AS latest
    FROM jarvis_memory jm
    WHERE jm.status = 'active'
    GROUP BY jm.content_type
    ORDER BY count DESC;
END;
$$;

COMMENT ON FUNCTION get_jarvis_stats IS 'Статистика записей памяти JARVIS по типам';

-- ================================================================
-- 8. Row Level Security (RLS)
-- ================================================================

ALTER TABLE jarvis_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis_agent_logs ENABLE ROW LEVEL SECURITY;

-- service_role (n8n, API) имеет полный доступ
CREATE POLICY "service_role_jarvis_memory" ON jarvis_memory
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "service_role_jarvis_projects" ON jarvis_projects
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "service_role_jarvis_agent_logs" ON jarvis_agent_logs
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- ================================================================
-- 9. Триггер для auto-update updated_at
-- ================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jarvis_memory_update_timestamp
    BEFORE UPDATE ON jarvis_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER jarvis_projects_update_timestamp
    BEFORE UPDATE ON jarvis_projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ================================================================
-- 10. Представление для аналитики
-- ================================================================

CREATE OR REPLACE VIEW jarvis_daily_activity AS
SELECT
    DATE(created_at) AS date,
    agent_id,
    COUNT(*) AS total_actions,
    COUNT(CASE WHEN status = 'success' THEN 1 END) AS successful,
    COUNT(CASE WHEN status = 'error' THEN 1 END) AS failed,
    AVG(duration_ms) AS avg_duration_ms
FROM jarvis_agent_logs
GROUP BY DATE(created_at), agent_id
ORDER BY date DESC;

COMMENT ON VIEW jarvis_daily_activity IS 'Ежедневная активность агентов JARVIS';
