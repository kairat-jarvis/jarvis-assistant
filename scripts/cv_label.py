"""cv_label.py — интерактивная разметка строк ntd.cross_validation_log.

После накопления 100–200 строк журнала эта утилита помогает эксперту-человеку
проставить итоговый вердикт: кто был прав (Claude / GPT-критик / оба / ни тот, ни другой),
дать комментарий. После разметки строка попадает в `ntd.cross_validation_labeled`
и доступна для экспорта в pre-training датасет (scripts/export_pretrain_dataset.py).

Использование:
    .venv/bin/python scripts/cv_label.py --next          # взять первый необработанный
    .venv/bin/python scripts/cv_label.py --id 17         # конкретный
    .venv/bin/python scripts/cv_label.py --only-disagree # только споры
    .venv/bin/python scripts/cv_label.py --stats         # сводка
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
NTD_PG_URL = os.getenv("NTD_PG_URL", "postgresql://localhost/expertise_ntd")

FINAL_OPTIONS = {
    "1": "claude_was_right",
    "2": "gpt_was_right",
    "3": "both_wrong",
    "4": "split",
    "s": None,
}
VERDICT_OPTIONS = {
    "a": "approved",
    "r": "rejected",
    "n": "need_more_evidence",
}


def open_conn():
    """Короткое autocommit-соединение. Раньше держали транзакцию открытой через
    весь ввод эксперта (input() может висеть часами) — это блокировало строку
    и удерживало idle-in-transaction слот в PG. Теперь читаем кандидата без
    FOR UPDATE, а на сохранение делаем оптимистичный UPDATE с условием
    expert_verdict IS NULL: если другой разметчик успел раньше, наш UPDATE
    тронет 0 строк и мы это увидим по rowcount.
    """
    return psycopg.connect(NTD_PG_URL, row_factory=dict_row, autocommit=True)


class RowLocked(Exception):
    """Строка уже размечена кем-то ещё (или была размечена до нашего UPDATE)."""


def fetch_one(conn, only_disagree: bool, row_id: int | None) -> dict | None:
    """Читаем кандидата без блокировки. Гонка решается на этапе update_row()
    через `WHERE expert_verdict IS NULL` + проверку rowcount."""
    with conn.cursor() as cur:
        if row_id is not None:
            cur.execute(
                "SELECT * FROM ntd.cross_validation_log "
                "WHERE id = %s AND expert_verdict IS NULL",
                (row_id,),
            )
        else:
            sql = """
                SELECT * FROM ntd.cross_validation_log
                WHERE expert_verdict IS NULL
                  AND (%s::boolean IS FALSE OR disagreement IS TRUE)
                ORDER BY id ASC
                LIMIT 1
            """
            cur.execute(sql, (only_disagree,))
        return cur.fetchone()


def update_row(conn, row_id: int, final_decision: str | None, expert_verdict: str | None, notes: str) -> None:
    """Оптимистичная запись: если кто-то параллельно уже разметил — RowLocked.

    Условие `expert_verdict IS NULL` в WHERE — это и есть наш «лок»: при гонке
    второй UPDATE отработает на нуле строк, что мы и поймаем по rowcount.
    """
    sql = """
        UPDATE ntd.cross_validation_log
        SET final_decision = %s,
            expert_verdict = %s,
            expert_notes   = %s,
            expert_at      = now()
        WHERE id = %s AND expert_verdict IS NULL
    """
    with conn.cursor() as cur:
        cur.execute(sql, (final_decision, expert_verdict, notes or None, row_id))
        if cur.rowcount == 0:
            raise RowLocked(f"id={row_id} уже был размечен параллельно — сохранение отменено")


def stats() -> None:
    sql = """
        SELECT
          count(*)                                                        AS total,
          count(*) FILTER (WHERE expert_verdict IS NULL)                  AS unlabeled,
          count(*) FILTER (WHERE expert_verdict IS NOT NULL)              AS labeled,
          count(*) FILTER (WHERE disagreement)                            AS disagreements,
          count(*) FILTER (WHERE disagreement AND expert_verdict IS NULL) AS unlabeled_disagree,
          count(*) FILTER (WHERE final_decision = 'claude_was_right')     AS claude_right,
          count(*) FILTER (WHERE final_decision = 'gpt_was_right')        AS gpt_right,
          count(*) FILTER (WHERE final_decision = 'both_wrong')           AS both_wrong,
          count(*) FILTER (WHERE final_decision = 'split')                AS split
        FROM ntd.cross_validation_log
    """
    with psycopg.connect(NTD_PG_URL, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(sql)
        s = cur.fetchone()
    print("📊 ntd.cross_validation_log:")
    for k, v in s.items():
        print(f"   {k:24s} {v}")


def _render_clauses(clauses: list, limit: int = 6) -> None:
    """Показываем retrieved-клозы, на которые опирался аналитик."""
    if not clauses:
        return
    print("📚 RETRIEVED КЛОЗЫ (top-{}):".format(min(limit, len(clauses))))
    for i, c in enumerate(clauses[:limit], 1):
        if not isinstance(c, dict):
            continue
        meta = c.get("metadata") or {}
        doc = meta.get("doc_code") or "НТД"
        clause = meta.get("clause_no") or meta.get("clause") or meta.get("number") or ""
        snippet = (c.get("content") or "").strip().replace("\n", " ")[:400]
        print(f"   [{i}] {doc} п.{clause}")
        print(textwrap.fill(snippet, width=78, initial_indent="       ", subsequent_indent="       "))


def render(row: dict) -> None:
    print("=" * 80)
    print(f"id={row['id']}   created={row['created_at']}   k={row['k_used']}")
    print(f"analyst={row['analyst_model']}   reviewer={row['reviewer_model']}")
    print(f"verdict={row['reviewer_verdict']}   disagreement={row['disagreement']}   "
          f"confidence={row['analyst_confidence']}")
    print("-" * 80)
    print("❓ ВОПРОС:")
    print(textwrap.fill(row["question"], width=80))
    print()
    _render_clauses(row.get("context_clauses") or [])
    print()
    print("🧠 ПОЛНЫЙ ОТВЕТ АНАЛИТИКА:")
    print(textwrap.fill(row["analyst_answer"] or "", width=80))
    if row.get("claim") and (row["claim"] or "").strip() != (row.get("analyst_answer") or "").strip()[:len(row["claim"])]:
        print()
        print("📌 CLAIM (выжимка):")
        print(textwrap.fill(row["claim"] or "", width=80))
    print()
    print("🔬 КРИТИКА:")
    print(textwrap.fill(row["gpt5_critique"] or "", width=80))
    if row["missed_norms"]:
        print()
        print("📚 Пропущенные нормы по мнению критика:")
        for n in row["missed_norms"]:
            print(f"   • {n}")
    print("=" * 80)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--next", action="store_true", help="взять первый необработанный")
    p.add_argument("--id", type=int, default=None)
    p.add_argument("--only-disagree", action="store_true")
    p.add_argument("--stats", action="store_true")
    args = p.parse_args()

    if args.stats:
        stats()
        return 0

    if not (args.next or args.id):
        print("Укажите --next, --id N или --stats")
        return 2

    # Autocommit + оптимистичный UPDATE: транзакция не открыта пока эксперт
    # читает кейс и думает. Гонка с параллельным разметчиком ловится по
    # rowcount=0 в update_row().
    with open_conn() as conn:
        row = fetch_one(conn, args.only_disagree, args.id)
        if not row:
            if args.id is not None:
                print(f"⚠ id={args.id}: либо не существует, либо уже размечен "
                      f"(expert_verdict IS NOT NULL). Перезапись запрещена.")
                return 1
            print("✅ Необработанных строк не найдено.")
            return 0

        render(row)

        print("\nКто прав?  [1] Claude  [2] GPT  [3] оба неправы  [4] split  [s] пропустить")
        choice = input("> ").strip().lower()
        if choice not in FINAL_OPTIONS:
            print("Отмена.")
            return 1
        final = FINAL_OPTIONS[choice]
        if final is None:
            print("Пропущено без записи.")
            return 0

        print("Итог: [a] approved  [r] rejected  [n] need_more_evidence")
        v = input("> ").strip().lower()
        expert_verdict = VERDICT_OPTIONS.get(v)
        if expert_verdict is None:
            print("Нужен a/r/n. Отмена.")
            return 1

        notes_required = final in {"gpt_was_right", "both_wrong", "split"}
        if notes_required:
            print("⚠ Для этого вердикта ОБЯЗАТЕЛЕН текстовый контр-ответ в notes")
            print("  (попадёт в SFT/DPO как ground truth). Пустая строка отменит запись.")
        print("Заметка (Enter — пусто):" if not notes_required else "Контр-ответ:")
        notes = input("> ").strip()
        if notes_required and not notes:
            print("✘ Пустые notes для этого вердикта запрещены. Отмена записи.")
            return 1

        try:
            update_row(conn, row["id"], final, expert_verdict, notes)
        except RowLocked as e:
            print(f"⏳ {e}")
            return 1
        print(f"✓ id={row['id']} обновлён: final={final} verdict={expert_verdict}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
