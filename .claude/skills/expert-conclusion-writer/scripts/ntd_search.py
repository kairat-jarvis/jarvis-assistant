#!/usr/bin/env python3
"""
ntd_search.py — поиск пунктов НТД для экспертных замечаний.

Использование:
    python ntd_search.py "расстояние дымовые извещатели"
    python ntd_search.py "ширина эвакуационного выхода" --doc "Кодекс № 235-V"
    python ntd_search.py "противопожарные двери EI" -n 5 --format remark
    python ntd_search.py --list-docs --type СП
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/kairat/Claude Code/JARVIS ASSISTANT")
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ntd_local import NtdLocal  # noqa: E402

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
R = "\033[0m"


def extract_text(content: str) -> str:
    """Извлекает секцию 'Текст:' из content пункта."""
    if "Текст:" in content:
        return content.split("Текст:", 1)[1].strip()
    return content.strip()


def format_plain(results: list[dict], n: int) -> None:
    shown = results[:n]
    print(f"\n{BOLD}Найдено: {len(results)} пунктов (показано {len(shown)}){R}\n")
    for i, r in enumerate(shown, 1):
        meta = r.get("metadata", {})
        doc = meta.get("doc_code", "?")
        clause = meta.get("clause_no", "?")
        section = meta.get("section_path", "")
        text = extract_text(r.get("content", ""))

        print(f"{BOLD}[{i}] {CYAN}{doc}{R}  п. {YELLOW}{clause}{R}")
        if section:
            print(f"     Раздел: {DIM}{section}{R}")
        print(f"     {text[:300]}")
        if len(text) > 300:
            print(f"     {DIM}... (ещё {len(text) - 300} симв.){R}")
        print()


def format_remark(results: list[dict], n: int) -> None:
    """Выводит первый результат в формате готового замечания (шаблон)."""
    if not results:
        print("Ничего не найдено.")
        return

    r = results[0]
    meta = r.get("metadata", {})
    doc = meta.get("doc_code", "?")
    clause = meta.get("clause_no", "?").lstrip("p.")
    text = extract_text(r.get("content", ""))

    print(f"\n{BOLD}── Шаблон замечания ──────────────────────────────────{R}")
    print(f"""
Замечание: [Раздел ПД, лист/чертёж NN].

[Описание нарушения в проектном решении] не соответствует требованиям
{doc}, п. {clause}:
«{text[:300]}».

Требуется: [Конкретное исправление].
""")

    if len(results) > 1:
        print(f"{DIM}── Дополнительные релевантные пункты ─────────────────{R}")
        for r2 in results[1:n]:
            m2 = r2.get("metadata", {})
            t2 = extract_text(r2.get("content", ""))
            print(f"  {CYAN}{m2.get('doc_code','?')}{R}  п. {m2.get('clause_no','?').lstrip('p.')}")
            print(f"  {DIM}{t2[:150]}{R}\n")


def format_citations(results: list[dict], n: int) -> None:
    """Компактный список цитат для вставки в заключение."""
    print()
    for r in results[:n]:
        meta = r.get("metadata", {})
        doc = meta.get("doc_code", "?")
        clause = meta.get("clause_no", "?").lstrip("p.")
        text = extract_text(r.get("content", ""))
        print(f"{CYAN}{doc}{R}, п. {YELLOW}{clause}{R}:")
        print(f'«{text[:250]}»')
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Поиск пунктов НТД для экспертных замечаний",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            '  python ntd_search.py "расстояние дымовые извещатели"\n'
            '  python ntd_search.py "ширина выхода" --doc "Кодекс № 235-V" -n 3\n'
            '  python ntd_search.py "противопожарные двери EI" --format remark\n'
            "  python ntd_search.py --list-docs --type СП\n"
        ),
    )
    parser.add_argument("query", nargs="?", help="Поисковый запрос (тема, требование, объект)")
    parser.add_argument("--doc", "-d", default=None, help="Ограничить поиск конкретным документом (doc_code)")
    parser.add_argument("-n", type=int, default=6, help="Количество результатов (default: 6)")
    parser.add_argument(
        "--format", "-f",
        choices=["plain", "remark", "cite"],
        default="plain",
        help="Формат вывода: plain (default) | remark (шаблон замечания) | cite (цитаты)",
    )
    parser.add_argument("--list-docs", action="store_true", help="Показать список документов в базе")
    parser.add_argument("--type", default=None, help="Фильтр по типу документа (СП, СН РК, …)")
    args = parser.parse_args()

    ntd = NtdLocal()

    if args.list_docs:
        docs = ntd.list_documents(doc_type=args.type, doc_status="active", limit=300)
        print(f"\n{BOLD}Документы в базе НТД{' (' + args.type + ')' if args.type else ''} — {len(docs)} шт.{R}\n")
        for d in docs:
            print(f"  {CYAN}{d['doc_code']:<35}{R}  {d.get('doc_type',''):12}  {d.get('doc_status','')}")
        return 0

    if not args.query:
        parser.print_help()
        return 1

    doc_codes = [args.doc] if args.doc else None
    results = ntd.fts_only(
        query_text=args.query,
        doc_codes=doc_codes,
        match_count=max(args.n * 2, 12),  # запрашиваем с запасом
    )

    if not results:
        print(f"\n{YELLOW}Ничего не найдено по запросу: «{args.query}»{R}")
        if doc_codes:
            print(f"Попробуйте без фильтра по документу: уберите --doc")
        return 0

    if args.format == "remark":
        format_remark(results, args.n)
    elif args.format == "cite":
        format_citations(results, args.n)
    else:
        format_plain(results, args.n)

    return 0


if __name__ == "__main__":
    sys.exit(main())
