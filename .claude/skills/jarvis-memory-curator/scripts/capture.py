#!/usr/bin/env python3
"""jarvis-memory-curator: сохранение записей в jarvis_memory.

Использование (CLI):
    python capture.py idea "Текст идеи" --tags jarvis,automation --priority high \
        --project "JARVIS ASSISTANT" --summary "Кратко"

    # из stdin:
    echo "Текст" | python capture.py decision --tags decision --project "JARVIS ASSISTANT"

Использование (Python):
    from capture import capture
    new_id = capture(content="...", content_type="idea", tags=["jarvis"], priority="high")
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Подключаем JarvisLocal из проекта
PROJECT_ROOT = Path("/Users/kairat/Claude Code/JARVIS ASSISTANT")
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.jarvis_local import JarvisLocal  # noqa: E402

VALID_TYPES = {"idea", "task", "note", "query", "decision", "context", "agent_report", "digest"}
VALID_PRIORITIES = {"critical", "high", "medium", "low"}


def _check_duplicates(cli: JarvisLocal, query: str, threshold: float = 0.6) -> list[dict]:
    """Возвращает близкие записи через FTS."""
    try:
        results = cli.fts_only(query=query, count=3)
    except Exception:
        return []
    return [r for r in (results or []) if r.get("similarity", 0) >= threshold]


def _resolve_project(cli: JarvisLocal, name: str | None) -> str | None:
    """Проверяет, что проект существует в jarvis_projects. Возвращает name или None."""
    if not name:
        return None
    with cli._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM jarvis_projects WHERE name = %s LIMIT 1", (name,))
        row = cur.fetchone()
        if row:
            return row["name"]
        # Fuzzy: найти по подстроке
        cur.execute(
            "SELECT name FROM jarvis_projects WHERE name ILIKE %s ORDER BY length(name) LIMIT 1",
            (f"%{name}%",),
        )
        row = cur.fetchone()
        return row["name"] if row else None


def capture(
    content: str,
    content_type: str,
    *,
    summary: str | None = None,
    tags: list[str] | None = None,
    priority: str = "medium",
    related_project: str | None = None,
    source: str = "claude_code_session",
    metadata: dict | None = None,
    check_duplicates: bool = True,
    embedding: list[float] | None = None,
) -> dict:
    """Сохраняет запись. Возвращает {'id', 'duplicates': [...] }."""

    if content_type not in VALID_TYPES:
        raise ValueError(f"content_type='{content_type}' не в {VALID_TYPES}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"priority='{priority}' не в {VALID_PRIORITIES}")

    cli = JarvisLocal()
    duplicates = _check_duplicates(cli, summary or content[:200]) if check_duplicates else []

    resolved_project = _resolve_project(cli, related_project)
    meta = dict(metadata or {})
    meta.setdefault("session_date", date.today().isoformat())
    if related_project and not resolved_project:
        meta["unresolved_project"] = related_project

    new_id = cli.add_memory(
        content=content,
        content_type=content_type,
        summary=summary,
        tags=tags or [],
        embedding=embedding,
        source=source,
        priority=priority,
        related_project=resolved_project,
        metadata=meta,
    )

    cli.log_action(
        agent_id="jarvis-memory-curator",
        action="add_memory",
        input_data={"content_type": content_type, "tags": tags, "project": resolved_project},
        output_data={"memory_id": new_id, "duplicates_found": len(duplicates)},
        status="success",
    )

    return {"id": new_id, "duplicates": duplicates, "resolved_project": resolved_project}


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS memory curator — single capture")
    parser.add_argument("content_type", choices=sorted(VALID_TYPES))
    parser.add_argument("content", nargs="?", help="Текст. Если опущен — читается stdin.")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--tags", default="", help="Через запятую")
    parser.add_argument("--priority", default="medium", choices=sorted(VALID_PRIORITIES))
    parser.add_argument("--project", dest="related_project", default=None)
    parser.add_argument("--source", default="claude_code_session")
    parser.add_argument("--metadata", default=None, help="JSON-строка")
    parser.add_argument("--no-dup-check", action="store_true")
    args = parser.parse_args()

    content = args.content
    if content is None or content == "-":
        content = sys.stdin.read().strip()
    if not content:
        print("ERROR: пустой content", file=sys.stderr)
        return 2

    metadata = json.loads(args.metadata) if args.metadata else None
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    result = capture(
        content=content,
        content_type=args.content_type,
        summary=args.summary,
        tags=tags,
        priority=args.priority,
        related_project=args.related_project,
        source=args.source,
        metadata=metadata,
        check_duplicates=not args.no_dup_check,
    )

    print(f"✓ Сохранено в jarvis_memory: id={result['id']}")
    if result["resolved_project"]:
        print(f"  related_project: {result['resolved_project']}")
    if result["duplicates"]:
        print(f"  ⚠ Найдено {len(result['duplicates'])} похожих записей (FTS sim ≥ 0.6):")
        for d in result["duplicates"]:
            print(f"    - [{d.get('content_type','?')}] {d.get('summary') or d.get('content','')[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
