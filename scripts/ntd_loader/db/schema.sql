PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Каждый запуск загрузчика на один PDF = одна запись runs.
-- При повторной обработке того же файла (тот же sha256) создаётся новый run,
-- но в pg-сторе INSERT идёт через ON CONFLICT DO UPDATE — данные не дублируются.
CREATE TABLE IF NOT EXISTS runs (
  id              TEXT    PRIMARY KEY,           -- uuid4
  started_at      TEXT    NOT NULL,
  finished_at     TEXT,
  status          TEXT    NOT NULL DEFAULT 'running',  -- running|ok|error|skipped
  pdf_path        TEXT    NOT NULL,
  pdf_sha256      TEXT    NOT NULL,
  doc_id          TEXT,                          -- uuid из ntd_documents (после insert)
  doc_code        TEXT,
  doc_title       TEXT,
  doc_year        INTEGER,
  total_pages     INTEGER NOT NULL DEFAULT 0,
  total_clauses   INTEGER NOT NULL DEFAULT 0,
  inserted_clauses INTEGER NOT NULL DEFAULT 0,
  updated_clauses INTEGER NOT NULL DEFAULT 0,
  embed_tokens    INTEGER NOT NULL DEFAULT 0,
  errors_count    INTEGER NOT NULL DEFAULT 0,
  duration_ms     INTEGER NOT NULL DEFAULT 0,
  notes           TEXT
);

-- Постраничный лог tier-эскалаций (pdfplumber / paddleocr / claude-vision).
-- Нужен для аудита Claude Vision fallback'ов (правило из CLAUDE.md: каждая
-- эскалация на L3 логируется отдельно).
CREATE TABLE IF NOT EXISTS pages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT    NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  page_no     INTEGER NOT NULL,
  tier        TEXT    NOT NULL,                  -- pdfplumber|paddleocr-vl-1.5|claude-vision
  confidence  REAL    NOT NULL,
  text_len    INTEGER NOT NULL DEFAULT 0,
  fallback_reason TEXT
);

-- Распарсенные клозы. Хранится только metadata + хэш, текст и эмбеддинг
-- уходят в Postgres clause_vectors. content_sha256 нужен чтобы при повторной
-- загрузке не пересчитывать embedding если текст не менялся.
CREATE TABLE IF NOT EXISTS clauses (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id          TEXT    NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  clause_pg_id    TEXT    NOT NULL,              -- = clause_vectors.id в Postgres
  clause_no       TEXT,
  section_path    TEXT,
  content_sha256  TEXT    NOT NULL,
  content_len     INTEGER NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'pending'  -- pending|inserted|updated|skipped|error
);

CREATE TABLE IF NOT EXISTS errors (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT    NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  occurred_at TEXT    NOT NULL DEFAULT (datetime('now')),
  phase       TEXT    NOT NULL,                  -- extract|parse|embed|store
  message     TEXT    NOT NULL,
  context     TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_pdf_sha    ON runs(pdf_sha256);
CREATE INDEX IF NOT EXISTS idx_runs_started    ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status     ON runs(status);
CREATE INDEX IF NOT EXISTS idx_pages_run       ON pages(run_id, page_no);
CREATE INDEX IF NOT EXISTS idx_pages_tier      ON pages(tier);
CREATE INDEX IF NOT EXISTS idx_clauses_run     ON clauses(run_id);
CREATE INDEX IF NOT EXISTS idx_clauses_pg      ON clauses(clause_pg_id);
CREATE INDEX IF NOT EXISTS idx_clauses_status  ON clauses(status);
CREATE INDEX IF NOT EXISTS idx_errors_run      ON errors(run_id);
