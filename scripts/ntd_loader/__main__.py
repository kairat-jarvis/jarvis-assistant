"""CLI для загрузчика НТД.

Примеры:
  # Один PDF, doc_code автоопределится из текста
  python -m scripts.ntd_loader /path/to/СН_РК_4.04-07-2023.pdf

  # Несколько PDF, явный doc_code не задаём
  python -m scripts.ntd_loader docs/*.pdf

  # Dry-run: только парсинг, без OpenAI и Postgres
  python -m scripts.ntd_loader file.pdf --dry-run

  # Переопределить doc_code если автодетект не сработал
  python -m scripts.ntd_loader file.pdf --doc-code "СН РК 1.04-26-2011"

  # Перезагрузить файл несмотря на успешный прошлый прогон
  python -m scripts.ntd_loader file.pdf --force

  # Журнал
  python -m scripts.ntd_loader --list
  python -m scripts.ntd_loader --show <run_id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Подтягиваем .env (OPENAI_API_KEY, ANTHROPIC_API_KEY, NTD_PG_URL) если установлен dotenv.
try:
    from dotenv import load_dotenv  # type: ignore

    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    # Совсем без зависимости: вручную распарсим простой .env (KEY=value, без кавычек).
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    _env_path = _PROJECT_ROOT / ".env"
    if _env_path.is_file():
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

from . import journal
from .loader import load_pdf


def _cmd_load(args: argparse.Namespace) -> int:
    exit_code = 0
    for pdf in args.pdfs:
        path = Path(pdf)
        if not path.exists():
            print(f"[skip] не найден: {pdf}", file=sys.stderr)
            exit_code = 1
            continue
        res = load_pdf(
            str(path),
            doc_code_override=args.doc_code,
            doc_title_override=args.doc_title,
            doc_year_override=args.doc_year,
            dry_run=args.dry_run,
            force=args.force,
        )
        print(
            f"  ↳ {path.name}: status={res.status} doc_code={res.doc_code!r} "
            f"clauses={res.total_clauses} ins/upd={res.inserted}/{res.updated} "
            f"tokens={res.embed_tokens} run_id={res.run_id}"
        )
        if res.status == "error":
            exit_code = 1
    return exit_code


def _cmd_list(args: argparse.Namespace) -> int:
    rows = journal.list_recent_runs(limit=args.limit)
    if not rows:
        print("журнал пуст")
        return 0
    print(
        f"{'run_id':36}  {'started':25}  {'status':8}  "
        f"{'doc_code':22}  {'pages':>5}  {'clauses':>7}  pdf"
    )
    for r in rows:
        print(
            f"{r['id']:36}  {r['started_at']:25}  {r['status']:8}  "
            f"{(r['doc_code'] or '-'):22}  {r['total_pages']:>5}  "
            f"{r['total_clauses']:>7}  {Path(r['pdf_path']).name}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    row = journal.run_summary(args.run_id)
    if not row:
        print(f"run {args.run_id} не найден", file=sys.stderr)
        return 1
    print(json.dumps(dict(row), ensure_ascii=False, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.ntd_loader",
        description="Загрузка НТД из PDF в локальный expertise_ntd с SQLite-журналом.",
    )
    p.add_argument("pdfs", nargs="*", help="один или несколько PDF-файлов")
    p.add_argument("--doc-code", help="явный doc_code (если автодетект не сработал)")
    p.add_argument("--doc-title", help="явный заголовок документа")
    p.add_argument("--doc-year", type=int, help="явный год")
    p.add_argument("--dry-run", action="store_true",
                   help="не писать в Postgres и в журнал, только парсинг")
    p.add_argument("--force", action="store_true",
                   help="перегружать даже если sha256 уже встречался с status=ok")
    p.add_argument("--list", action="store_true", help="показать последние прогоны")
    p.add_argument("--limit", type=int, default=20, help="лимит для --list")
    p.add_argument("--show", metavar="RUN_ID", help="показать детали прогона")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list:
        return _cmd_list(args)
    if args.show:
        args.run_id = args.show
        return _cmd_show(args)
    if not args.pdfs:
        _build_parser().print_help()
        return 2
    return _cmd_load(args)


if __name__ == "__main__":
    raise SystemExit(main())
