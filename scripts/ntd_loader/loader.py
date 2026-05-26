"""Главный pipeline загрузчика НТД."""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Делаем доступным импорт vypiska_ird, когда модуль запускают как
# `python -m scripts.ntd_loader ...` из корня JARVIS ASSISTANT.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from openai import OpenAI

from . import journal, pg_store
from .parser import (
    detect_doc_code,
    detect_doc_title,
    detect_doc_year,
    iter_clause_payloads,
    parse_clauses,
)

log = logging.getLogger("ntd_loader")

EMBEDDING_MODEL = os.environ.get("NTD_EMBEDDING_MODEL", "text-embedding-3-small")
EMBED_BATCH = int(os.environ.get("NTD_EMBED_BATCH", "64"))


@dataclass
class LoadResult:
    run_id: str
    status: str                  # ok|skipped|error
    doc_id: Optional[str]
    doc_code: Optional[str]
    total_clauses: int
    inserted: int
    updated: int
    embed_tokens: int
    errors_count: int
    notes: Optional[str] = None


def _sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _embed_batched(client: OpenAI, texts: list[str]) -> tuple[list[list[float]], int]:
    """Возвращает (embeddings, total_tokens) пачками по EMBED_BATCH."""
    out: list[list[float]] = []
    tokens = 0
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
        tokens += getattr(resp.usage, "total_tokens", 0) or 0
    return out, tokens


def load_pdf(
    pdf_path: str,
    *,
    doc_code_override: Optional[str] = None,
    doc_title_override: Optional[str] = None,
    doc_year_override: Optional[int] = None,
    dry_run: bool = False,
    force: bool = False,
    progress_print: bool = True,
) -> LoadResult:
    """Грузит один PDF.

    force=True заставляет переобработать файл даже если sha256 уже встречался с status=ok.
    dry_run=True не пишет ни в Postgres, ни в SQLite-журнал (только парсит и считает).
    """
    pdf = Path(pdf_path).resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)

    started_ms = int(time.time() * 1000)
    sha = _sha256(pdf)

    if not dry_run:
        prev = journal.find_successful_run(sha)
        if prev and not force:
            return LoadResult(
                run_id=prev["id"],
                status="skipped",
                doc_id=prev["doc_id"],
                doc_code=prev["doc_code"],
                total_clauses=prev["total_clauses"],
                inserted=0,
                updated=0,
                embed_tokens=0,
                errors_count=0,
                notes=f"already loaded as {prev['id']} on {prev['started_at']}",
            )
        run_id = journal.start_run(str(pdf), sha)
    else:
        run_id = "dry-run"

    errors_count = 0
    total_pages = 0
    inserted = updated = 0
    embed_tokens = 0

    try:
        # ── 1. extract via waterfall ─────────────────────────────────────────
        # Импортируем лениво: парсер/журнал не должны тянуть pdfplumber и PaddleOCR.
        from vypiska_ird.ird_extract.ocr_waterfall import extract_pdf
        if progress_print:
            print(f"[ntd_loader] extract: {pdf.name}", flush=True)
        full_text, pages = extract_pdf(str(pdf))
        total_pages = len(pages)
        if not dry_run:
            for idx, p in enumerate(pages, start=1):
                journal.log_page(
                    run_id, idx, p.tier, p.confidence, len(p.text), p.fallback_reason
                )

        # ── 2. detect doc meta ───────────────────────────────────────────────
        doc_code = doc_code_override or detect_doc_code(full_text)
        if not doc_code:
            msg = "doc_code не найден в тексте; задайте --doc-code"
            if not dry_run:
                journal.log_error(run_id, "parse", msg)
                journal.finish_run(
                    run_id, status="error", total_pages=total_pages,
                    errors_count=1, duration_ms=int(time.time() * 1000) - started_ms,
                    notes=msg,
                )
            raise ValueError(msg)

        doc_title = doc_title_override or detect_doc_title(full_text, doc_code)
        doc_year = doc_year_override or detect_doc_year(full_text)

        # ── 3. parse clauses ─────────────────────────────────────────────────
        clauses = parse_clauses(full_text)
        if progress_print:
            print(
                f"[ntd_loader] parsed: doc_code={doc_code!r}, "
                f"clauses={len(clauses)}, pages={total_pages}",
                flush=True,
            )
        if not clauses:
            msg = "ни один клоз не распознан (проверьте PDF или эвристику парсера)"
            if not dry_run:
                journal.log_error(run_id, "parse", msg)
                journal.finish_run(
                    run_id, status="error", total_pages=total_pages,
                    errors_count=1, duration_ms=int(time.time() * 1000) - started_ms,
                    notes=msg,
                )
            return LoadResult(
                run_id=run_id, status="error", doc_id=None, doc_code=doc_code,
                total_clauses=0, inserted=0, updated=0, embed_tokens=0,
                errors_count=1, notes=msg,
            )

        payloads = list(iter_clause_payloads(doc_code, clauses))
        contents = [p[0] for p in payloads]
        metadatas = [p[1] for p in payloads]

        # ── 4. dry-run выход до OpenAI и Postgres ────────────────────────────
        if dry_run:
            for c in clauses[:5]:
                print(f"  · {c.clause_no:>10} | {c.section_path:<20} | {c.body[:80]}…")
            if len(clauses) > 5:
                print(f"  · … и ещё {len(clauses) - 5} клозов")
            return LoadResult(
                run_id="dry-run", status="ok", doc_id=None, doc_code=doc_code,
                total_clauses=len(clauses), inserted=0, updated=0, embed_tokens=0,
                errors_count=0, notes="dry-run",
            )

        # ── 5. upsert document, дёрнуть doc_id для clause_pg_id ──────────────
        conn = pg_store.connect()
        try:
            doc_id = pg_store.upsert_document(
                conn,
                pg_store.DocMeta(
                    doc_code=doc_code,
                    doc_title=doc_title,
                    doc_year=doc_year,
                    source_file_name=pdf.name,
                    source_file_id=sha,
                ),
            )
            journal.set_doc_meta(run_id, doc_id, doc_code, doc_title, doc_year)
            if progress_print:
                print(f"[ntd_loader] doc_id={doc_id}", flush=True)

            # ── 6. embed batched ─────────────────────────────────────────────
            if progress_print:
                print(
                    f"[ntd_loader] embedding {len(contents)} clauses "
                    f"({EMBEDDING_MODEL})…",
                    flush=True,
                )
            client = OpenAI()
            embeddings, embed_tokens = _embed_batched(client, contents)
            if len(embeddings) != len(contents):
                raise RuntimeError(
                    f"embeddings count mismatch: {len(embeddings)} vs {len(contents)}"
                )

            # ── 7. upsert clauses ────────────────────────────────────────────
            rows = [
                pg_store.ClauseRow(
                    clause_pg_id=pg_store.make_clause_pg_id(doc_id, m["clause_no"]),
                    content=c,
                    metadata=m,
                    embedding=e,
                )
                for c, m, e in zip(contents, metadatas, embeddings)
            ]
            inserted, updated = pg_store.upsert_clauses(conn, rows)

            # ── 8. log clauses в журнал (после успешного upsert) ─────────────
            for c, m, content in zip(clauses, metadatas, contents):
                pid = pg_store.make_clause_pg_id(doc_id, m["clause_no"])
                journal.log_clause(
                    run_id, pid, c.clause_no, c.section_path,
                    _content_sha256(content), len(content),
                    "inserted",  # детальный статус insert vs update не различаем здесь
                )
        finally:
            conn.close()

        duration_ms = int(time.time() * 1000) - started_ms
        journal.finish_run(
            run_id, status="ok",
            total_pages=total_pages, total_clauses=len(clauses),
            inserted_clauses=inserted, updated_clauses=updated,
            embed_tokens=embed_tokens, errors_count=errors_count,
            duration_ms=duration_ms,
        )
        if progress_print:
            print(
                f"[ntd_loader] ok: inserted={inserted}, updated={updated}, "
                f"tokens={embed_tokens}, took={duration_ms} ms",
                flush=True,
            )
        return LoadResult(
            run_id=run_id, status="ok", doc_id=doc_id, doc_code=doc_code,
            total_clauses=len(clauses), inserted=inserted, updated=updated,
            embed_tokens=embed_tokens, errors_count=errors_count,
        )

    except Exception as exc:
        log.exception("ntd_loader failed")
        if not dry_run:
            journal.log_error(
                run_id, "pipeline", str(exc)[:500], traceback.format_exc()[:2000]
            )
            journal.finish_run(
                run_id, status="error",
                total_pages=total_pages, total_clauses=0,
                inserted_clauses=inserted, updated_clauses=updated,
                embed_tokens=embed_tokens, errors_count=errors_count + 1,
                duration_ms=int(time.time() * 1000) - started_ms,
                notes=str(exc)[:500],
            )
        return LoadResult(
            run_id=run_id, status="error", doc_id=None, doc_code=None,
            total_clauses=0, inserted=inserted, updated=updated,
            embed_tokens=embed_tokens, errors_count=errors_count + 1,
            notes=str(exc)[:500],
        )
