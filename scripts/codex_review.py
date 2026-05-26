"""codex_review.py — ревью проекта и локальной базы НТД через gpt-5.1-codex.

Собирает:
  • исходники нового pipeline (ntd_ask_with_review, cv_label, export_pretrain_dataset,
    схема cross_validation_schema.sql);
  • дамп структуры expertise_ntd (ntd_documents, clause_vectors, ntd.cross_validation_log)
    и счётчики, сэмпл клозов;

Отправляет в gpt-5.1-codex (Responses API, reasoning=high) с инструкцией:
ревью кода + здравомыслия схемы БД + поиск багов/уязвимостей/анти-паттернов.

Результат: out/codex_review_<UTC>.md (+ stdout).

Использование:
    .venv/bin/python scripts/codex_review.py
    .venv/bin/python scripts/codex_review.py --model gpt-5.1-codex-max
    .venv/bin/python scripts/codex_review.py --effort medium
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

REVIEW_FILES = [
    "scripts/ntd_ask_with_review.py",
    "scripts/cv_label.py",
    "scripts/export_pretrain_dataset.py",
    "db/cross_validation_schema.sql",
    "scripts/ntd_local.py",
]

DB = "expertise_ntd"
PROBES = [
    ("ntd_documents columns",      r"\d ntd_documents"),
    ("clause_vectors columns",     r"\d clause_vectors"),
    ("ntd.cross_validation_log",   r"\d ntd.cross_validation_log"),
    ("counts",                     "SELECT (SELECT count(*) FROM ntd_documents) AS docs, "
                                   "(SELECT count(*) FROM clause_vectors) AS clauses, "
                                   "(SELECT count(*) FROM ntd.cross_validation_log) AS logs;"),
    ("sample clause",              "SELECT id, metadata->>'doc_code' AS doc, metadata->>'clause' AS cl, "
                                   "left(content, 300) AS preview FROM clause_vectors LIMIT 3;"),
    ("cvlog rows",                 "SELECT id, reviewer_verdict, disagreement, final_decision, "
                                   "expert_verdict, array_length(missed_norms,1) AS missed "
                                   "FROM ntd.cross_validation_log ORDER BY id;"),
]

PROMPT = """\
Ты — senior reviewer. Перед тобой код и схема локальной системы кросс-валидации
ответов LLM по нормам РК. Стек: Python 3 (psycopg v3, openai, anthropic), \
PostgreSQL 17 + pgvector, эмбеддинги text-embedding-3-small.

Зачем нужен код: пользователь задаёт вопрос → hybrid_search по 90k клозов → \
Claude (аналитик) даёт ответ → GPT-5 (независимый ревьюер) выдаёт verdict в JSON →\
строка пишется в ntd.cross_validation_log → человек размечает через cv_label.py →\
после 100-200 размеченных кейсов экспортируется SFT/DPO датасет.

Сделай ревью по пунктам:

1. БАГИ И КОРРЕКТНОСТЬ. SQL-инъекции, race conditions, утечки соединений, \
обработка пустых/NULL значений, ошибки парсинга JSON, ошибки в bcrypt/auth (если есть). \
Не общие фразы — конкретные строки и фиксы.

2. СХЕМА БД. Адекватны ли индексы под планируемые запросы (фильтр по \
disagreement, expert_verdict IS NULL, gin по missed_norms)? Какие миграции \
понадобятся при росте до 100k+ строк? Нужны ли партиционирование, retention?

3. БЕЗОПАСНОСТЬ. Логирование PII (вопросы пользователей могут содержать имена), \
размер JSONB полей (reviewer_raw без ограничения), отсутствие RLS \
(допустимо для локальной БД, но проверь).

4. КАЧЕСТВО ДАННЫХ ДЛЯ ОБУЧЕНИЯ. Корректен ли выбор winning_answer() в \
export_pretrain_dataset.py? Не теряются ли metadata? Достаточно ли разнообразия?

5. АРХИТЕКТУРНЫЕ ВОПРОСЫ. Где код стоит вытащить в общий модуль, где \
дублируется логика, что неудобно для расширения (например, добавление \
третьего ревьюера, ансамбль вердиктов).

6. УЯЗВИМОСТЬ К ХАЛЛЮЦИНАЦИЯМ. Текущий ANALYST_SYSTEM запрещает \
экстраполяцию — достаточно ли этого? Какие ещё guard-rails добавить в промпт \
или в pre-processing клозов?

Формат ответа: маркдаун с разделами по 1-6, в каждом — пункты вида \
«файл:строка → проблема → конкретная правка». Без воды и без \
повторения постановки задачи. Самые важные пункты помечай ⚠️.
"""


def gather_files() -> str:
    parts = ["# ИСХОДНИКИ"]
    for rel in REVIEW_FILES:
        p = ROOT / rel
        if not p.exists():
            parts.append(f"\n## {rel}\n[файл не найден]")
            continue
        parts.append(f"\n## {rel}\n```")
        parts.append(p.read_text(encoding="utf-8"))
        parts.append("```")
    return "\n".join(parts)


def gather_db() -> str:
    parts = ["# СОСТОЯНИЕ БАЗЫ expertise_ntd"]
    for name, sql in PROBES:
        out = subprocess.run(
            ["psql", DB, "-c", sql],
            capture_output=True, text=True, timeout=30,
        )
        parts.append(f"\n## {name}\n```\n{out.stdout.strip()}\n```")
        if out.returncode != 0:
            parts.append(f"```stderr\n{out.stderr.strip()}\n```")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.1-codex")
    ap.add_argument("--effort", default="high", choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    from openai import OpenAI
    cli = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    payload = "\n\n".join([PROMPT, gather_files(), gather_db()])
    chars = len(payload)
    print(f"📦 payload: {chars} символов ({chars/4:.0f} токенов оценочно)")
    print(f"🤖 модель: {args.model}   reasoning: {args.effort}")

    print("⏳ запрос в Responses API (reasoning может занять 30-120с)...")
    resp = cli.responses.create(
        model=args.model,
        input=payload,
        reasoning={"effort": args.effort},
    )

    text = resp.output_text or ""
    usage = getattr(resp, "usage", None)

    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.output) if args.output else out_dir / f"codex_review_{stamp}.md"

    header = [
        f"# Codex Review — {stamp}",
        f"- model: `{args.model}`",
        f"- reasoning: `{args.effort}`",
    ]
    if usage:
        try:
            header.append(f"- usage: input={usage.input_tokens}, output={usage.output_tokens}, "
                          f"reasoning={getattr(usage, 'output_tokens_details', {}).get('reasoning_tokens', '?') if hasattr(usage,'output_tokens_details') else '?'}")
        except Exception:
            pass
    out_path.write_text("\n".join(header) + "\n\n" + text, encoding="utf-8")

    print(f"✅ ответ записан → {out_path}")
    print("=" * 80)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
