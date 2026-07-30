"""Миграция данных JARVIS из Supabase в локальный PostgreSQL (jarvis_local).

Архитектурно аналогично expertise-orchestrator/scripts/migrate-ntd-*.ts:
  - страничная подгрузка из источника
  - ON CONFLICT (id) DO UPDATE в назначении
  - идемпотентно (можно перезапускать)

Поддерживает два источника:
  1. --from-mcp-dump <file>   — JSON-дамп, отданный Supabase MCP execute_sql
                                (обходит отсутствие service_role_key)
  2. --from-supabase           — прямой PostgREST с SUPABASE_SERVICE_ROLE_KEY
                                (страничная пагинация по id)

Запуск:
  .venv/bin/python scripts/migrate_jarvis_from_supabase.py \\
      --from-mcp-dump /path/to/dump.txt
  .venv/bin/python scripts/migrate_jarvis_from_supabase.py --from-supabase

Env:
  JARVIS_PG_URL=postgresql://localhost/jarvis_local           (назначение)
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY                     (для --from-supabase)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg
from psycopg.types.json import Json

JARVIS_PG_URL = os.getenv("JARVIS_PG_URL", "postgresql://localhost/jarvis_local")
PAGE = 500
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MEMORY_COLS = (
    "id", "content", "content_type", "summary", "tags", "embedding",
    "source", "priority", "status", "related_project", "metadata",
    "created_at", "updated_at",
)
PROJECT_COLS = (
    "id", "name", "description", "status", "agents", "key_decisions",
    "created_at", "updated_at",
)
LOG_COLS = (
    "id", "agent_id", "action", "input_data", "output_data",
    "status", "duration_ms", "created_at",
)


# ──────────────────────────────────────────────────────────────────────────
# Источник 1: MCP-дамп (один большой JSON, обёрнутый в MCP-плёнку)
# ──────────────────────────────────────────────────────────────────────────
def load_from_mcp_dump(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    # MCP-обёртка: {"result":"...<untrusted-data-...>JSON</untrusted-data-...>..."}
    try:
        outer = json.loads(raw)
        inner_text = outer.get("result", raw)
    except json.JSONDecodeError:
        inner_text = raw
    m = re.search(r"<untrusted-data-[^>]+>\s*(\[.*?\])\s*</untrusted-data-",
                  inner_text, re.DOTALL)
    if not m:
        m = re.search(r"(\[\s*\{.*\}\s*\])", inner_text, re.DOTALL)
    if not m:
        raise RuntimeError("Не нашёл JSON-массив в дампе")
    rows = json.loads(m.group(1))
    if not rows or "dump" not in rows[0]:
        raise RuntimeError("Дамп должен быть результатом SELECT json_build_object(...) AS dump")
    return rows[0]["dump"]


# ──────────────────────────────────────────────────────────────────────────
# Источник 2: PostgREST (для штатной периодической миграции)
# ──────────────────────────────────────────────────────────────────────────
class PostgREST:
    def __init__(self, base_url: str, key: str):
        self.base = base_url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }

    def fetch_page(self, table: str, after_id: str | None) -> list[dict]:
        params = {"select": "*", "order": "id.asc", "limit": str(PAGE)}
        if after_id:
            params["id"] = f"gt.{after_id}"
        url = f"{self.base}/{table}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def fetch_all(self, table: str) -> list[dict]:
        out: list[dict] = []
        after: str | None = None
        while True:
            page = self.fetch_page(table, after)
            if not page:
                break
            out.extend(page)
            after = page[-1]["id"]
            if len(page) < PAGE:
                break
        return out


def load_from_supabase() -> dict:
    url = os.getenv("SUPABASE_URL")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or
           os.getenv("SUPABASE_ANON_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY (или ANON) обязательны")
    cli = PostgREST(url, key)
    return {
        "memory":     cli.fetch_all("jarvis_memory"),
        "projects":   cli.fetch_all("jarvis_projects"),
        "agent_logs": cli.fetch_all("jarvis_agent_logs"),
    }


# ──────────────────────────────────────────────────────────────────────────
# Назначение: upsert по id
# ──────────────────────────────────────────────────────────────────────────
def upsert(conn: psycopg.Connection, table: str, cols: tuple[str, ...],
           rows: list[dict]) -> int:
    if not rows:
        return 0
    # table/cols приходят только из констант этого модуля (MEMORY_COLS и т.п.),
    # но проверяем формат явно — это единственное, что стоит между f-string и SQL-инъекцией
    if not _IDENTIFIER_RE.match(table):
        raise ValueError(f"Небезопасное имя таблицы: {table!r}")
    for c in cols:
        if not _IDENTIFIER_RE.match(c):
            raise ValueError(f"Небезопасное имя колонки: {c!r}")

    placeholders = ",".join(["%s"] * len(cols))
    col_list = ",".join(cols)
    update_set = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {update_set}"
    )
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            values = []
            for c in cols:
                v = r.get(c)
                # JSON-типы -> Json wrapper
                if c in ("metadata", "input_data", "output_data", "key_decisions"):
                    values.append(Json(v) if v is not None else None)
                # embedding приходит из MCP-дампа строкой '[0.1,0.2,...]' —
                # psycopg примет её как vector благодаря implicit cast (pgvector).
                else:
                    values.append(v)
            try:
                cur.execute(sql, values)
                conn.commit()
                n += 1
            except Exception as exc:
                # коммитим построчно: битая строка откатывает только себя,
                # а не уже вставленные до неё строки этой же таблицы
                conn.rollback()
                print(f"  [WARN] {table}: пропущена строка id={r.get('id')}: {exc}",
                      file=sys.stderr)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-mcp-dump", type=Path, metavar="FILE")
    g.add_argument("--from-supabase", action="store_true")
    ap.add_argument("--truncate", action="store_true",
                    help="Очистить таблицы назначения перед заливкой")
    args = ap.parse_args()

    print(f"Назначение: {JARVIS_PG_URL}")

    if args.from_mcp_dump:
        print(f"Источник:   MCP-дамп {args.from_mcp_dump}")
        dump = load_from_mcp_dump(args.from_mcp_dump)
    else:
        print(f"Источник:   {os.getenv('SUPABASE_URL')}")
        dump = load_from_supabase()

    counts = {k: len(dump.get(k) or []) for k in ("memory", "projects", "agent_logs")}
    print(f"Получено:   memory={counts['memory']}  projects={counts['projects']}  agent_logs={counts['agent_logs']}")

    with psycopg.connect(JARVIS_PG_URL) as conn:
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE jarvis_memory, jarvis_projects, jarvis_agent_logs")
            conn.commit()
            print("TRUNCATE выполнен")

        n_mem = upsert(conn, "jarvis_memory",     MEMORY_COLS,  dump.get("memory")     or [])
        n_prj = upsert(conn, "jarvis_projects",   PROJECT_COLS, dump.get("projects")   or [])
        n_log = upsert(conn, "jarvis_agent_logs", LOG_COLS,     dump.get("agent_logs") or [])

    print(f"Залито:     memory={n_mem}  projects={n_prj}  agent_logs={n_log}")
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
