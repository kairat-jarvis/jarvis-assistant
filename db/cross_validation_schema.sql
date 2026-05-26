-- ============================================================================
-- ntd.cross_validation_log — журнал кросс-валидации Claude-аналитика
-- независимым GPT-эксперт-критиком (логика из expertise-orchestrator/re-verify).
--
-- Применение:
--     psql expertise_ntd -f db/cross_validation_schema.sql
--
-- Зачем:
--   1. Каждый запуск ntd_ask_with_review пишет строку. Поле `disagreement`
--      выставляется в TRUE для verdict in ('rejected','uncertain').
--   2. Поля final_decision / expert_verdict / expert_notes — для пометки
--      человеком-экспертом (postmortem). До разметки они NULL.
--   3. После 100–200 размеченных кейсов таблица служит датасетом для
--      пре-обучения (SFT/DPO): см. scripts/export_pretrain_dataset.py.
--
-- Идемпотентно: IF NOT EXISTS / CREATE OR REPLACE.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS ntd;

CREATE TABLE IF NOT EXISTS ntd.cross_validation_log (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),

    -- Вход
    question        text NOT NULL,
    context_clauses jsonb NOT NULL DEFAULT '[]'::jsonb,    -- top-K из hybrid_search
    k_used          int,
    embed_model     text,

    -- Раунд 1: аналитик
    analyst_model     text NOT NULL,
    analyst_answer    text NOT NULL,
    analyst_confidence text,            -- "high" | "medium" | "low" | NULL
    claim             text,             -- сжатая выжимка ключевого утверждения (необязательно)
    claude_reasoning  text,             -- полная цепочка рассуждений (== analyst_answer обычно)

    -- Раунд 2: независимый критик
    reviewer_model     text NOT NULL,
    reviewer_verdict   text NOT NULL CHECK (reviewer_verdict IN
                          ('confirmed','rejected','uncertain','error')),
    gpt5_critique      text NOT NULL,   -- rationale из JSON-ответа критика
    missed_norms       text[] NOT NULL DEFAULT '{}',
    reviewer_raw       jsonb NOT NULL DEFAULT '{}'::jsonb, -- полный JSON ответа критика

    -- Сводка
    disagreement       boolean NOT NULL,    -- true если verdict != 'confirmed'
    final_decision     text CHECK (final_decision IS NULL OR final_decision IN
                          ('claude_was_right','gpt_was_right','both_wrong','split')),
    expert_verdict     text CHECK (expert_verdict IS NULL OR expert_verdict IN
                          ('approved','rejected','need_more_evidence')),
    expert_notes       text,
    expert_at          timestamptz,         -- когда проставлено human-review

    metadata           jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- CHECK-констрейнты на текстовые enum-поля. Добавляются отдельно от CREATE TABLE,
-- чтобы работали и для уже существующих таблиц (CREATE TABLE IF NOT EXISTS
-- пропускает блок целиком, поэтому inline-CHECK на staging-БД не применится).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'cvlog_final_decision_chk' AND conrelid = 'ntd.cross_validation_log'::regclass
    ) THEN
        ALTER TABLE ntd.cross_validation_log
            ADD CONSTRAINT cvlog_final_decision_chk
            CHECK (final_decision IS NULL OR final_decision IN
                   ('claude_was_right','gpt_was_right','both_wrong','split'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'cvlog_expert_verdict_chk' AND conrelid = 'ntd.cross_validation_log'::regclass
    ) THEN
        ALTER TABLE ntd.cross_validation_log
            ADD CONSTRAINT cvlog_expert_verdict_chk
            CHECK (expert_verdict IS NULL OR expert_verdict IN
                   ('approved','rejected','need_more_evidence'));
    END IF;
    -- gpt_was_right / both_wrong / split требуют контр-ответ в expert_notes —
    -- без него строка бесполезна для SFT/DPO (см. export_pretrain_dataset.py).
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'cvlog_notes_required_chk' AND conrelid = 'ntd.cross_validation_log'::regclass
    ) THEN
        ALTER TABLE ntd.cross_validation_log
            ADD CONSTRAINT cvlog_notes_required_chk
            CHECK (
                final_decision IS NULL
                OR final_decision = 'claude_was_right'
                OR (expert_notes IS NOT NULL AND length(btrim(expert_notes)) > 0)
            );
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_cvlog_created_at  ON ntd.cross_validation_log (created_at DESC);
-- Заменили бесполезный partial-index по самой колонке disagreement (внутри
-- WHERE-фильтра значения одинаковые, планировщик его не использует) на
-- индекс по дате — ускоряет «последние N спорных кейсов» и админ-выборки.
CREATE INDEX IF NOT EXISTS idx_cvlog_disagree_recent
    ON ntd.cross_validation_log (created_at DESC)
    WHERE disagreement IS TRUE;
CREATE INDEX IF NOT EXISTS idx_cvlog_verdict     ON ntd.cross_validation_log (reviewer_verdict);
CREATE INDEX IF NOT EXISTS idx_cvlog_unlabeled   ON ntd.cross_validation_log (id) WHERE expert_verdict IS NULL;
-- Горячий путь cv_label.py --only-disagree: первый необработанный спор.
CREATE INDEX IF NOT EXISTS idx_cvlog_unlabeled_disagree
    ON ntd.cross_validation_log (id)
    WHERE expert_verdict IS NULL AND disagreement IS TRUE;
CREATE INDEX IF NOT EXISTS idx_cvlog_metadata    ON ntd.cross_validation_log USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_cvlog_missed_norm ON ntd.cross_validation_log USING gin (missed_norms);

-- Удобная вьюха: только размеченные строки готовые к экспорту в датасет
CREATE OR REPLACE VIEW ntd.cross_validation_labeled AS
SELECT *
FROM ntd.cross_validation_log
WHERE expert_verdict IS NOT NULL
  AND final_decision IS NOT NULL;

COMMENT ON TABLE  ntd.cross_validation_log        IS 'Журнал кросс-валидации (Claude-аналитик vs GPT-критик). Источник датасета для pre-training.';
COMMENT ON COLUMN ntd.cross_validation_log.claim  IS 'Краткая выжимка ключевого утверждения аналитика, по которому идёт спор.';
COMMENT ON COLUMN ntd.cross_validation_log.final_decision IS 'Кто прав после разбора: claude_was_right | gpt_was_right | both_wrong | split.';
COMMENT ON VIEW   ntd.cross_validation_labeled    IS 'Только размеченные людьми строки — готовы для экспорта в SFT/DPO датасет.';
