"""Запись документа и клозов в локальный expertise_ntd.

Контракт схемы — см. db/REDIRECT.md и память [[reference-ntd-local-vs-supabase]].
Колонки clause_id в локальной clause_vectors НЕТ — используем id формата
'{doc_id}-{clause_no}' как primary key.

Идемпотентность:
  - ntd_documents: по doc_code (UNIQUE-семантика через ON CONFLICT) — обновляем title/year.
  - clause_vectors: id detuministичен от (doc_id, clause_no) — ON CONFLICT DO UPDATE.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

import psycopg
from psycopg.rows import dict_row

NTD_PG_URL = os.environ.get("NTD_PG_URL", "postgresql://localhost/expertise_ntd")


def _emb_literal(values: list[float]) -> str:
    """pgvector-литерал без потери точности (без pgvector-python-пакета)."""
    return "[" + ",".join(repr(float(x)) for x in values) + "]"


def connect() -> psycopg.Connection:
    """Открывает соединение с НТД-БД. Короткоживущее, без кэша."""
    return psycopg.connect(NTD_PG_URL, row_factory=dict_row)


# ─── ntd_documents ────────────────────────────────────────────────────────────

@dataclass
class DocMeta:
    doc_code: str
    doc_title: Optional[str] = None
    doc_type: Optional[str] = None  # 'СН', 'СП', 'ГОСТ' и т.п. (выводится из doc_code)
    doc_year: Optional[int] = None
    doc_status: str = "active"
    source_file_name: Optional[str] = None
    source_file_id: Optional[str] = None  # sha256 файла


def _doc_type_from_code(doc_code: str) -> Optional[str]:
    """Первое слово doc_code — тип документа ('СН РК ...' → 'СН')."""
    parts = doc_code.split()
    return parts[0] if parts else None


def upsert_document(conn: psycopg.Connection, meta: DocMeta) -> str:
    """Возвращает doc_id (UUID). Если документ с таким doc_code уже есть — апдейтит meta."""
    doc_type = meta.doc_type or _doc_type_from_code(meta.doc_code)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM ntd_documents WHERE doc_code = %s LIMIT 1",
            (meta.doc_code,),
        )
        row = cur.fetchone()
        if row:
            doc_id = str(row["id"])
            cur.execute(
                """
                UPDATE ntd_documents SET
                  doc_title = COALESCE(%s, doc_title),
                  doc_type  = COALESCE(%s, doc_type),
                  doc_year  = COALESCE(%s, doc_year),
                  doc_status = COALESCE(%s, doc_status),
                  source_file_name = COALESCE(%s, source_file_name),
                  source_file_id   = COALESCE(%s, source_file_id),
                  updated_at = now()
                WHERE id = %s
                """,
                (
                    meta.doc_title, doc_type, meta.doc_year, meta.doc_status,
                    meta.source_file_name, meta.source_file_id, doc_id,
                ),
            )
        else:
            doc_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO ntd_documents
                  (id, doc_code, doc_title, doc_type, doc_year, doc_status,
                   source_file_name, source_file_id, loaded_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                """,
                (
                    doc_id, meta.doc_code, meta.doc_title, doc_type,
                    meta.doc_year, meta.doc_status,
                    meta.source_file_name, meta.source_file_id,
                ),
            )
    conn.commit()
    return doc_id


# ─── clause_vectors ───────────────────────────────────────────────────────────

@dataclass
class ClauseRow:
    clause_pg_id: str          # '{doc_id}-{clause_no}'
    content: str
    metadata: dict
    embedding: list[float]


def make_clause_pg_id(doc_id: str, clause_no: str) -> str:
    return f"{doc_id}-{clause_no}"


def upsert_clauses(
    conn: psycopg.Connection,
    rows: Iterable[ClauseRow],
) -> tuple[int, int]:
    """Возвращает (inserted, updated). ON CONFLICT смотрит по PK clause_vectors.id."""
    inserted = updated = 0
    import json as _json
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO clause_vectors (id, content, metadata, embedding)
                VALUES (%s, %s, %s::jsonb, %s::vector)
                ON CONFLICT (id) DO UPDATE SET
                  content = EXCLUDED.content,
                  metadata = EXCLUDED.metadata,
                  embedding = EXCLUDED.embedding
                RETURNING (xmax = 0) AS inserted
                """,
                (r.clause_pg_id, r.content, _json.dumps(r.metadata, ensure_ascii=False),
                 _emb_literal(r.embedding)),
            )
            ins = cur.fetchone()["inserted"]
            if ins:
                inserted += 1
            else:
                updated += 1
    conn.commit()
    return inserted, updated


def fetch_existing_clause_hashes(
    conn: psycopg.Connection, doc_id: str
) -> dict[str, str]:
    """Возвращает {clause_pg_id: md5(content)} — для skip-логики при повторной загрузке."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, md5(content) AS h FROM clause_vectors WHERE id LIKE %s",
            (f"{doc_id}-%",),
        )
        return {r["id"]: r["h"] for r in cur.fetchall()}
