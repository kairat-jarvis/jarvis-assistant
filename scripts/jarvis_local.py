"""Локальный клиент памяти JARVIS — drop-in замена Supabase RPC.

Сигнатуры match_jarvis_memory / get_jarvis_stats идентичны Supabase.
Гибридный поиск (hybrid_search_jarvis_memory) — новая локальная RPC
(BM25 + cosine + RRF) для случаев, когда нужна более релевантная выдача
по русскому тексту.

    from scripts.jarvis_local import JarvisLocal
    cli = JarvisLocal()  # postgresql://localhost/jarvis_local

    # семантический поиск
    cli.match_memory(embed, threshold=0.65, count=10, type_="idea")

    # гибридный (рекомендуется при наличии и текста, и эмбеддинга)
    cli.hybrid_search("вентиляция складов", embed, count=8)

    # FTS-fallback / запрос без эмбеддинга
    cli.fts_only("вентиляция складов", count=8)

    # статистика
    cli.stats()

    # CRUD
    cli.add_memory(content="...", content_type="idea", embedding=embed,
                   tags=["jarvis"], metadata={"feasibility_score": 8})
"""
from __future__ import annotations

import os
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

JARVIS_PG_URL = os.getenv("JARVIS_PG_URL", "postgresql://localhost/jarvis_local")


def _vec(values: Iterable[float] | None) -> str | None:
    if values is None:
        return None
    return "[" + ",".join(f"{float(x):.7g}" for x in values) + "]"


class JarvisLocal:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or JARVIS_PG_URL

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    # ── Поиск ─────────────────────────────────────────────────────────────

    def match_memory(
        self,
        query_embedding: list[float],
        threshold: float = 0.7,
        count: int = 10,
        type_: str | None = None,
        status: str | None = "active",
    ) -> list[dict[str, Any]]:
        """Чисто векторный поиск — аналог Supabase match_jarvis_memory."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM match_jarvis_memory(%s::vector, %s, %s, %s, %s)",
                (_vec(query_embedding), threshold, count, type_, status),
            )
            return cur.fetchall()

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        count: int = 8,
        candidates: int = 40,
        k_rrf: int = 60,
        type_: str | None = None,
        status: str | None = "active",
    ) -> list[dict[str, Any]]:
        """Гибридный поиск (BM25+cosine RRF) — локальное расширение API."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hybrid_search_jarvis_memory(%s, %s::vector, %s, %s, %s, %s, %s)",
                (query_text, _vec(query_embedding), count, candidates, k_rrf, type_, status),
            )
            return cur.fetchall()

    def fts_only(
        self,
        query_text: str,
        count: int = 8,
        type_: str | None = None,
        status: str | None = "active",
    ) -> list[dict[str, Any]]:
        """Полнотекстовый поиск без эмбеддинга — годится для запросов на лету."""
        sql = """
            SELECT id, content, content_type, summary, tags, metadata, related_project,
                   ts_rank(fts, plainto_tsquery('russian', %s)) AS fts_score
            FROM jarvis_memory
            WHERE fts @@ plainto_tsquery('russian', %s)
              AND (%s::text IS NULL OR content_type = %s)
              AND (%s::text IS NULL OR status       = %s)
            ORDER BY fts_score DESC
            LIMIT %s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (query_text, query_text, type_, type_, status, status, count))
            return cur.fetchall()

    def stats(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM get_jarvis_stats()")
            return cur.fetchall()

    # ── Запись ────────────────────────────────────────────────────────────

    def add_memory(
        self,
        content: str,
        content_type: str,
        *,
        summary: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        source: str = "user",
        priority: str = "medium",
        status: str = "active",
        related_project: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        sql = """
            INSERT INTO jarvis_memory
              (content, content_type, summary, tags, embedding, source,
               priority, status, related_project, metadata)
            VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s::jsonb)
            RETURNING id::text
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (
                content, content_type, summary, tags or [],
                _vec(embedding), source, priority, status,
                related_project, Json(metadata or {}),
            ))
            row = cur.fetchone()
            conn.commit()
            return row["id"]

    def log_action(
        self,
        agent_id: str,
        action: str,
        *,
        input_data: dict | None = None,
        output_data: dict | None = None,
        status: str = "success",
        duration_ms: int | None = None,
    ) -> str:
        sql = """
            INSERT INTO jarvis_agent_logs
              (agent_id, action, input_data, output_data, status, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id::text
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (
                agent_id, action,
                Json(input_data)  if input_data  is not None else None,
                Json(output_data) if output_data is not None else None,
                status, duration_ms,
            ))
            row = cur.fetchone()
            conn.commit()
            return row["id"]


if __name__ == "__main__":
    cli = JarvisLocal()
    with cli._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM jarvis_memory")
        n_mem = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM jarvis_agent_logs")
        n_log = cur.fetchone()["n"]
    print(f"JARVIS_PG_URL = {cli.dsn}")
    print(f"  jarvis_memory:     {n_mem}")
    print(f"  jarvis_agent_logs: {n_log}")
    print("\nstats():")
    for r in cli.stats():
        print(f"  {r['content_type']:12s} {r['count']:>3d}  latest={r['latest']}")
    print("\nfts_only('JARVIS'):")
    for r in cli.fts_only("JARVIS", count=3):
        print(f"  [{r['content_type']}] {r.get('summary') or (r['content'] or '')[:80]}")
