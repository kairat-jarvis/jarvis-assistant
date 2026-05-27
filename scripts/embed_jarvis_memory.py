"""embed_jarvis_memory.py — генерация эмбеддингов для jarvis_memory.

Берёт строки с embedding IS NULL из локального jarvis_local, считает
text-embedding-3-small (1536-dim) по `content + summary` и обновляет
строку in-place. Опционально (--sync-supabase) тем же эмбеддингом
обновляет Supabase-зеркало через PostgREST PATCH, чтобы n8n тоже
работали с заполненной памятью.

Использование:
    .venv/bin/python scripts/embed_jarvis_memory.py
    .venv/bin/python scripts/embed_jarvis_memory.py --sync-supabase
    .venv/bin/python scripts/embed_jarvis_memory.py --batch 16 --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

JARVIS_PG_URL = os.getenv("JARVIS_PG_URL", "postgresql://localhost/jarvis_local")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
MODEL = "text-embedding-3-small"  # 1536-dim, совпадает с vector(1536) в схеме


def _vec(values) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in values) + "]"


def _build_input(row: dict) -> str:
    parts = [row.get("summary") or "", row.get("content") or ""]
    text = "\n".join(p for p in parts if p).strip()
    return text[:8000]  # обрезаем — у модели лимит ~8191 токенов, символьный safe-margin


def fetch_pending(conn, limit: int | None) -> list[dict]:
    sql = """
        SELECT id::text AS id, content, summary
        FROM jarvis_memory
        WHERE embedding IS NULL
        ORDER BY created_at
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=MODEL, input=texts)
    return [d.embedding for d in resp.data]


def update_local(conn, rows: list[tuple[str, list[float]]]) -> None:
    with conn.cursor() as cur:
        for rid, emb in rows:
            cur.execute(
                "UPDATE jarvis_memory SET embedding = %s::vector WHERE id = %s",
                (_vec(emb), rid),
            )
    conn.commit()


def sync_supabase(rows: list[tuple[str, list[float]]]) -> int:
    """PATCH в Supabase (если SUPABASE_SERVICE_ROLE_KEY доступен)."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("⚠️  SUPABASE_SERVICE_ROLE_KEY не задан — пропускаем sync с Supabase.")
        return 0

    import json
    import urllib.request

    ok = 0
    for rid, emb in rows:
        url = f"{SUPABASE_URL}/rest/v1/jarvis_memory?id=eq.{rid}"
        payload = json.dumps({"embedding": emb}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            method="PATCH",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if 200 <= r.status < 300:
                    ok += 1
        except Exception as e:
            print(f"   ⚠️  Supabase PATCH {rid[:8]}: {e}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=16, help="размер батча для OpenAI")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число строк (для теста)")
    parser.add_argument("--dry-run", action="store_true", help="не писать в БД, только показать")
    parser.add_argument("--sync-supabase", action="store_true", help="параллельно обновлять Supabase")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY не задан (.env)")
        return 2

    client = OpenAI()

    with psycopg.connect(JARVIS_PG_URL, row_factory=dict_row) as conn:
        rows = fetch_pending(conn, args.limit)
        if not rows:
            print("✅ Все строки уже имеют embedding.")
            return 0

        print(f"🔍 К обработке: {len(rows)} строк, модель={MODEL}, batch={args.batch}")
        total_done = 0
        t0 = time.time()

        for i in range(0, len(rows), args.batch):
            chunk = rows[i:i + args.batch]
            inputs = [_build_input(r) for r in chunk]
            empty_idx = [j for j, t in enumerate(inputs) if not t]
            if empty_idx:
                print(f"   ⚠️  Пустой текст у {len(empty_idx)} строк — пропускаем.")
                chunk = [c for j, c in enumerate(chunk) if j not in empty_idx]
                inputs = [t for j, t in enumerate(inputs) if j not in empty_idx]
            if not chunk:
                continue

            embs = embed_batch(client, inputs)
            pairs = list(zip([r["id"] for r in chunk], embs))

            if args.dry_run:
                for r, emb in zip(chunk, embs):
                    print(f"   [dry] {r['id'][:8]} dim={len(emb)} text={_build_input(r)[:60]!r}")
            else:
                update_local(conn, pairs)
                if args.sync_supabase:
                    n = sync_supabase(pairs)
                    print(f"   ↪️  Supabase обновлено: {n}/{len(pairs)}")

            total_done += len(pairs)
            print(f"   ✓ {total_done}/{len(rows)}")

        print(f"\n✅ Готово за {time.time() - t0:.1f}s. Обновлено: {total_done}")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FILTER (WHERE embedding IS NULL) AS empty, count(*) AS total FROM jarvis_memory"
            )
            stat = cur.fetchone()
        print(f"📊 jarvis_memory: всего={stat['total']}, без embedding={stat['empty']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
