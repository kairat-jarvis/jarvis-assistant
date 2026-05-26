"""Локальный клиент НТД — drop-in замена Supabase RPC.

Подключается к локальному PostgreSQL (NTD_PG_URL), использует те же
функции, что и в Supabase: match_clauses, hybrid_search_clauses,
fts_only_search_clauses. Сигнатуры и возвращаемые поля совпадают —
переключение Supabase → local требует только смены конструктора клиента.

Использование:
    from scripts.ntd_local import NtdLocal
    cli = NtdLocal()  # postgresql://localhost/expertise_ntd

    # 1) hybrid (BM25 + cosine + RRF) — основной рабочий метод
    hits = cli.hybrid_search(
        query_text="требования к АПС складских помещений",
        query_embedding=embed,         # list[float] длины 1536
        doc_codes=["СП РК 2.02"],     # ILIKE-pattern; None/[] = без фильтра
        match_count=8,
    )

    # 2) чисто векторный
    hits = cli.match_clauses(query_embedding=embed, match_count=10,
                             filter={"doc_code": "СН РК 4.02-01-2017"})

    # 3) FTS-fallback (когда embedding-провайдер упал)
    hits = cli.fts_only(query_text="...", doc_codes=None, match_count=8)

Эмбеддинги генерируются на стороне вызывающего (OpenAI text-embedding-3-small).
"""
from __future__ import annotations

import os
from typing import Any, Iterable

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Json

NTD_PG_URL = os.getenv("NTD_PG_URL", "postgresql://localhost/expertise_ntd")


def _vec(values: Iterable[float]) -> list[float]:
    """list[float] для биндинга через pgvector-адаптер.

    Раньше тут вручную собирался текстовый литерал '[v1,v2,...]' с округлением
    до 7 значащих цифр — для 1536-мерного embedding это заметно искажало
    cosine-расстояния и заставляло PG парсить длинную строку. Теперь полная
    точность float и бинарный wire-protocol через register_vector().
    """
    return [float(x) for x in values]


class NtdLocal:
    """Тонкий клиент к локальной БД НТД.

    Открывает короткое соединение под каждый вызов — на пуле уровня
    приложения построим отдельно, если потребуется.
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or NTD_PG_URL

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        register_vector(conn)
        return conn

    # ── Supabase-совместимые RPC ──────────────────────────────────────────

    def match_clauses(
        self,
        query_embedding: list[float],
        match_count: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Чисто векторный поиск — аналог Supabase RPC match_clauses."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM match_clauses(%s::vector, %s, %s::jsonb)",
                (_vec(query_embedding), match_count, Json(filter or {})),
            )
            return cur.fetchall()

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        doc_codes: list[str] | None = None,
        match_count: int = 8,
        candidates: int = 40,
        k_rrf: int = 60,
    ) -> list[dict[str, Any]]:
        """Гибридный поиск (BM25+cosine с RRF) — аналог hybrid_search_clauses."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hybrid_search_clauses(%s, %s::vector, %s, %s, %s, %s)",
                (
                    query_text,
                    _vec(query_embedding),
                    doc_codes or None,
                    match_count,
                    candidates,
                    k_rrf,
                ),
            )
            return cur.fetchall()

    def fts_only(
        self,
        query_text: str,
        doc_codes: list[str] | None = None,
        match_count: int = 8,
        candidates: int = 40,
    ) -> list[dict[str, Any]]:
        """FTS-fallback (без embedding) — аналог fts_only_search_clauses."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fts_only_search_clauses(%s, %s, %s, %s)",
                (query_text, doc_codes or None, match_count, candidates),
            )
            return cur.fetchall()

    # ── Каталожные операции (по таблице ntd_documents) ────────────────────

    def get_document(self, doc_code: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ntd_documents WHERE doc_code = %s LIMIT 1",
                (doc_code,),
            )
            return cur.fetchone()

    def list_documents(
        self,
        doc_type: str | None = None,
        doc_status: str | None = "Действует",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ntd_documents WHERE TRUE"
        args: list[Any] = []
        if doc_type:
            sql += " AND doc_type = %s"
            args.append(doc_type)
        if doc_status:
            sql += " AND doc_status = %s"
            args.append(doc_status)
        sql += " ORDER BY doc_code LIMIT %s"
        args.append(limit)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()


# ── CLI / smoke-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cli = NtdLocal()
    with cli._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS docs FROM ntd_documents")
        d = cur.fetchone()
        cur.execute("SELECT count(*) AS clauses FROM clause_vectors")
        c = cur.fetchone()
    print(f"NTD_PG_URL = {cli.dsn}")
    print(f"  ntd_documents: {d['docs']}")
    print(f"  clause_vectors: {c['clauses']}")
    # FTS-smoketest (не требует эмбеддинга)
    sample = cli.fts_only(query_text="автоматическая пожарная сигнализация",
                          doc_codes=None, match_count=3)
    print(f"  fts_only(АПС): {len(sample)} попаданий")
    for row in sample:
        meta = row.get("metadata") or {}
        print(f"    - {meta.get('doc_code', '?')} {meta.get('clause_no', '')}: "
              f"{(row.get('content') or '')[:80]}...")
