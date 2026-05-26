"""SQLite-журнал прогонов загрузчика НТД.

Паттерн взят из expertise-orchestrator/db/store.ts:
  - ленивый singleton getDb()
  - схема единым файлом, применяется через exec() при первом открытии
  - PRAGMA WAL + foreign_keys = ON
  - upsert через ON CONFLICT DO UPDATE

Файл БД лежит рядом с кодом: scripts/ntd_loader/data/ntd_ingest.db.
WAL-побочки (.db-shm, .db-wal) — нормально, в gitignore.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

_HERE = Path(__file__).resolve().parent
_SCHEMA_PATH = _HERE / "db" / "schema.sql"
_DB_PATH = _HERE / "data" / "ntd_ingest.db"

_conn: Optional[sqlite3.Connection] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    """Открывает соединение лениво, применяет схему один раз."""
    global _conn
    if _conn is not None:
        return _conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _conn = conn
    return conn


def db_path() -> Path:
    return _DB_PATH


# ─── runs ─────────────────────────────────────────────────────────────────────

def start_run(pdf_path: str, pdf_sha256: str) -> str:
    """Создаёт запись runs(status=running) и возвращает run_id."""
    run_id = str(uuid.uuid4())
    get_db().execute(
        "INSERT INTO runs (id, started_at, status, pdf_path, pdf_sha256) "
        "VALUES (?, ?, 'running', ?, ?)",
        (run_id, _now_iso(), pdf_path, pdf_sha256),
    )
    return run_id


def set_doc_meta(
    run_id: str,
    doc_id: Optional[str],
    doc_code: Optional[str],
    doc_title: Optional[str],
    doc_year: Optional[int],
) -> None:
    get_db().execute(
        "UPDATE runs SET doc_id=?, doc_code=?, doc_title=?, doc_year=? WHERE id=?",
        (doc_id, doc_code, doc_title, doc_year, run_id),
    )


def finish_run(
    run_id: str,
    *,
    status: str,
    total_pages: int = 0,
    total_clauses: int = 0,
    inserted_clauses: int = 0,
    updated_clauses: int = 0,
    embed_tokens: int = 0,
    errors_count: int = 0,
    duration_ms: int = 0,
    notes: Optional[str] = None,
) -> None:
    get_db().execute(
        """
        UPDATE runs SET
          finished_at=?, status=?,
          total_pages=?, total_clauses=?, inserted_clauses=?, updated_clauses=?,
          embed_tokens=?, errors_count=?, duration_ms=?, notes=?
        WHERE id=?
        """,
        (
            _now_iso(), status,
            total_pages, total_clauses, inserted_clauses, updated_clauses,
            embed_tokens, errors_count, duration_ms, notes,
            run_id,
        ),
    )


def find_successful_run(pdf_sha256: str) -> Optional[sqlite3.Row]:
    """Возвращает последний успешный run для PDF — для skip-логики."""
    cur = get_db().execute(
        "SELECT * FROM runs WHERE pdf_sha256=? AND status='ok' "
        "ORDER BY started_at DESC LIMIT 1",
        (pdf_sha256,),
    )
    return cur.fetchone()


# ─── pages ────────────────────────────────────────────────────────────────────

def log_page(
    run_id: str,
    page_no: int,
    tier: str,
    confidence: float,
    text_len: int,
    fallback_reason: Optional[str] = None,
) -> None:
    get_db().execute(
        "INSERT INTO pages (run_id, page_no, tier, confidence, text_len, fallback_reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, page_no, tier, confidence, text_len, fallback_reason),
    )


# ─── clauses ──────────────────────────────────────────────────────────────────

def log_clause(
    run_id: str,
    clause_pg_id: str,
    clause_no: Optional[str],
    section_path: Optional[str],
    content_sha256: str,
    content_len: int,
    status: str,
) -> None:
    get_db().execute(
        "INSERT INTO clauses "
        "(run_id, clause_pg_id, clause_no, section_path, content_sha256, content_len, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, clause_pg_id, clause_no, section_path, content_sha256, content_len, status),
    )


# ─── errors ───────────────────────────────────────────────────────────────────

def log_error(run_id: str, phase: str, message: str, context: Optional[str] = None) -> None:
    get_db().execute(
        "INSERT INTO errors (run_id, phase, message, context) VALUES (?, ?, ?, ?)",
        (run_id, phase, message[:2000], context),
    )


# ─── reporting helpers ────────────────────────────────────────────────────────

def list_recent_runs(limit: int = 20) -> list[sqlite3.Row]:
    cur = get_db().execute(
        "SELECT id, started_at, finished_at, status, pdf_path, doc_code, "
        "total_pages, total_clauses, inserted_clauses, errors_count "
        "FROM runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )
    return cur.fetchall()


def run_summary(run_id: str) -> Optional[sqlite3.Row]:
    cur = get_db().execute("SELECT * FROM runs WHERE id=?", (run_id,))
    return cur.fetchone()


@contextmanager
def closing_db() -> Iterator[sqlite3.Connection]:
    """Контекст-менеджер для CLI: закрывает соединение по выходу."""
    global _conn
    db = get_db()
    try:
        yield db
    finally:
        if _conn is not None:
            _conn.close()
            _conn = None
