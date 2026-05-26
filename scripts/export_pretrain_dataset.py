"""export_pretrain_dataset.py — экспорт ntd.cross_validation_labeled в JSONL.

Производит датасет для пре-обучения (fine-tuning) на размеченных кейсах
журнала кросс-валидации НТД. Поддерживает два формата:

  • SFT  — Supervised Fine-Tuning, OpenAI chat-format:
       {"messages": [
           {"role": "system",    "content": ANALYST_SYSTEM},
           {"role": "user",      "content": "вопрос + клозы"},
           {"role": "assistant", "content": "корректный ответ"}
       ]}
     Корректным ответом считается:
       - оригинальный ответ аналитика, если final_decision = 'claude_was_right'
       - критика GPT-эксперта, если final_decision = 'gpt_was_right'
       - конкатенация expert_notes (если есть), иначе — пропуск.

  • DPO  — Direct Preference Optimization, пара chosen/rejected:
       {"prompt": ..., "chosen": ..., "rejected": ...}
     Включает только реальные расхождения (disagreement = true) с разметкой
     final_decision in ('claude_was_right','gpt_was_right'). chosen — победитель,
     rejected — проигравший. Это самые ценные строки для дообучения критика.

  • both — оба формата.

Использование:
    .venv/bin/python scripts/export_pretrain_dataset.py --format sft   --output out/
    .venv/bin/python scripts/export_pretrain_dataset.py --format dpo   --output out/
    .venv/bin/python scripts/export_pretrain_dataset.py --format both  --output out/
    .venv/bin/python scripts/export_pretrain_dataset.py --min-cases 100 ...

При --min-cases N: если размеченных строк меньше N, выходит с предупреждением
и кодом 3 (для CI/cron-проверок «достигли ли порога»).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
NTD_PG_URL = os.getenv("NTD_PG_URL", "postgresql://localhost/expertise_ntd")

ANALYST_SYSTEM = (
    "Ты — главный эксперт государственной экспертизы РК по проектной документации. "
    "Отвечай по приведённым клозам НТД, цитируй doc_code и пункт. "
    "Не экстраполируй условие одного клоза на параметры другого. "
    "Если данных нет — прямо скажи «нет данных в базе». В конце указывай confidence."
)

REVIEWER_SYSTEM = (
    "Ты — независимый эксперт государственной экспертизы РК. Тебе дан вопрос инженера, "
    "ответ другого эксперта и список клозов НТД. Выдай JSON-вердикт: "
    '{"verdict":"confirmed|rejected|uncertain","rationale":"...","missed_norms":[...]}. '
    "confirmed = ответ корректен и подкреплён клозами. rejected = противоречит нормам. "
    "uncertain = данных недостаточно."
)


def iter_labeled(batch_size: int = 500) -> Iterable[dict]:
    """Стримим размеченные строки через named-cursor — массив context_clauses
    тяжёлый, при 100k+ строк fetchall() съест всю память."""
    sql = "SELECT * FROM ntd.cross_validation_labeled ORDER BY id"
    with psycopg.connect(NTD_PG_URL, row_factory=dict_row) as conn:
        with conn.cursor(name="cv_labeled_export") as cur:
            cur.itersize = batch_size
            cur.execute(sql)
            for row in cur:
                yield row


def count_labeled() -> int:
    with psycopg.connect(NTD_PG_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ntd.cross_validation_labeled")
        return cur.fetchone()[0]


def format_user_prompt(row: dict) -> str:
    clauses = row.get("context_clauses") or []
    parts = [f"ВОПРОС:\n{row['question']}", "", "КЛОЗЫ ИЗ БАЗЫ НТД:"]
    for i, c in enumerate(clauses, 1):
        meta = (c.get("metadata") or {}) if isinstance(c, dict) else {}
        doc = meta.get("doc_code") or "НТД"
        clause = meta.get("clause_no") or meta.get("clause") or meta.get("number") or ""
        content = (c.get("content") or "").strip().replace("\n", " ")[:800]
        parts.append(f"[{i}] {doc} п.{clause}\n{content}")
    return "\n\n".join(parts)


# Жёсткий формат маркера: «confidence: high|medium|low» (можно `=`). Слабый
# паттерн `confidence[\s:=\-–—]*([a-zа-я]+)` пропускал «confidencelevel»/
# «confidence: высокая» и маркеры в произвольном месте — это ломало контракт
# ANALYST_SYSTEM «маркер в самом конце ответа».
CONFIDENCE_MARKER_RE = re.compile(
    r"confidence\s*[:=]\s*(high|medium|low)\b",
    re.IGNORECASE,
)
# Маркер должен быть в последней непустой строке. Это сильнее, чем «в последних
# N символах»: после конкатенации с expert_notes старый маркер мог оказаться в
# середине, а это считается некорректным финалом для модели.
_LAST_LINE_MARKER_RE = re.compile(
    r"^\s*confidence\s*[:=]\s*(high|medium|low)\s*$",
    re.IGNORECASE,
)


def _ensure_confidence_marker(text: str, default: str = "medium") -> str:
    """ANALYST_SYSTEM требует завершать ответ маркером `confidence: high|medium|low`.

    Контракт: маркер должен быть в **последней непустой строке** ответа.
    - Если последняя строка уже такая — оставляем как есть.
    - Иначе вырезаем все «старые» маркеры из тела (чтобы не плодить дубликаты
      после конкатенации с expert_notes) и приклеиваем валидный в самый конец.

    Без этого SFT/DPO ломают _extract_confidence() на инференсе и downstream-метрики.
    """
    if not text:
        return text
    stripped = text.rstrip()
    if not stripped:
        return text
    lines = stripped.splitlines()
    last_non_empty = next((ln for ln in reversed(lines) if ln.strip()), "")
    if _LAST_LINE_MARKER_RE.match(last_non_empty):
        return text
    body = CONFIDENCE_MARKER_RE.sub("", stripped).rstrip()
    return f"{body}\nconfidence: {default}"


def winning_answer(row: dict) -> str | None:
    """Что считать «правильным» ответом для SFT.

    Для gpt_was_right ground truth = expert_notes (человеческий нормативный ответ).
    Критика ревьюера — это мета-комментарий, а не альтернативный ответ; её
    использование как target учит модель писать ревью, а не отвечать по нормам.
    Если эксперт не записал контр-ответ — строка исключается из SFT.

    Любой target проходит через _ensure_confidence_marker: ANALYST_SYSTEM
    обязывает finish-line «confidence: ...», иначе обученная модель забудет
    маркер и логирование сломается.
    """
    final = row.get("final_decision")
    notes = (row.get("expert_notes") or "").strip()
    target: str | None = None
    if final == "claude_was_right":
        # notes здесь — обычно короткое уточнение («добавь ссылку на 5.4»),
        # а не самостоятельный ответ. Заменять основной текст этим обрывком
        # нельзя — конкатенируем как пометку эксперта поверх ответа аналитика.
        base = (row["analyst_answer"] or "").strip()
        if notes:
            target = f"{base}\n\n[уточнение эксперта]\n{notes}" if base else notes
        else:
            target = base or None
    elif final == "gpt_was_right":
        target = notes or None
    elif final == "both_wrong":
        target = notes or None
    elif final == "split":
        target = notes or None
    if not target:
        return None
    return _ensure_confidence_marker(target)


def to_sft(rows: Iterable[dict]) -> Iterable[dict]:
    for row in rows:
        target = winning_answer(row)
        if not target:
            continue
        yield {
            "messages": [
                {"role": "system", "content": ANALYST_SYSTEM},
                {"role": "user", "content": format_user_prompt(row)},
                {"role": "assistant", "content": target},
            ],
            "metadata": {
                "log_id": row["id"],
                "final_decision": row.get("final_decision"),
                "expert_verdict": row.get("expert_verdict"),
                "reviewer_verdict": row.get("reviewer_verdict"),
                "analyst_model": row.get("analyst_model"),
                "reviewer_model": row.get("reviewer_model"),
                "k_used": row.get("k_used"),
            },
        }


def to_dpo(rows: Iterable[dict]) -> Iterable[dict]:
    """DPO-пары: chosen vs rejected — оба должны быть полноценными ответами.

    Включаем только gpt_was_right с заполненным expert_notes:
        chosen   = expert_notes  (нормативный контр-ответ человека)
        rejected = analyst_answer

    claude_was_right исключаем: rejected-кандидата нет (критика — не альтернативный
    ответ; expert_notes обычно подтверждают, а не опровергают). Когда в схеме
    появится отдельное поле для «плохого» альтернативного ответа — расширим.
    """
    for row in rows:
        final = row.get("final_decision")
        if final != "gpt_was_right":
            continue
        if not row.get("disagreement"):
            continue
        notes = (row.get("expert_notes") or "").strip()
        if not notes:
            continue
        analyst = row["analyst_answer"]
        if not analyst:
            continue
        # ANALYST_SYSTEM добавляется в prompt, иначе обучение пойдёт без той
        # системной инструкции, которая всегда присутствует на инференсе
        # (см. ntd_ask_with_review.ask_analyst → system=ANALYST_SYSTEM).
        prompt = f"[SYSTEM]\n{ANALYST_SYSTEM}\n\n[USER]\n{format_user_prompt(row)}"
        # Оба ответа в DPO-паре должны соответствовать тому же контракту
        # «confidence в конце», иначе модель выучит шаблон без маркера и сломает
        # _extract_confidence() на инференсе.
        chosen = _ensure_confidence_marker(notes)
        rejected = _ensure_confidence_marker(analyst)
        yield {
            "prompt": prompt,
            "chosen": chosen,
            "rejected": rejected,
            "metadata": {
                "log_id": row["id"],
                "final_decision": final,
                "disagreement": row.get("disagreement"),
                "reviewer_verdict": row.get("reviewer_verdict"),
                "expert_verdict": row.get("expert_verdict"),
                # Per-model quality analysis: без этих полей нельзя оценить,
                # какой analyst_model генерит больше rejected'ов в датасете.
                "analyst_model": row.get("analyst_model"),
                "reviewer_model": row.get("reviewer_model"),
                "k_used": row.get("k_used"),
            },
        }


def to_dpo_critic(rows: Iterable[dict]) -> Iterable[dict]:
    """DPO-пары для обучения критика на кейсах `claude_was_right` со спором.

    Симметричный набор к to_dpo(): там аналитик ошибся и учится у эксперта;
    здесь — критик ошибочно отклонил/усомнился, и учится подтверждать корректные
    ответы. Без этого потока критик-модель смещается в сторону агрессивных
    отклонений (см. codex review #33).

    prompt   = REVIEWER_SYSTEM + вопрос + ответ аналитика + клозы
    chosen   = правильный JSON-вердикт {"verdict":"confirmed", ...}
    rejected = реальный (ошибочный) reviewer_raw как JSON-строка
    """
    for row in rows:
        if row.get("final_decision") != "claude_was_right":
            continue
        if not row.get("disagreement"):
            continue
        analyst = (row.get("analyst_answer") or "").strip()
        if not analyst:
            continue
        reviewer_raw = row.get("reviewer_raw") or {}
        if not isinstance(reviewer_raw, dict) or not reviewer_raw:
            continue
        # Реальный вердикт должен быть rejected/uncertain — это и есть «rejected»
        # пример для обучения. confirmed-кейс мимо disagreement не пройдёт, но
        # ловим явные ошибки логирования.
        bad_verdict = (reviewer_raw.get("verdict") or "").lower()
        if bad_verdict not in {"rejected", "uncertain"}:
            continue
        notes = (row.get("expert_notes") or "").strip()
        good_verdict = {
            "verdict": "confirmed",
            "rationale": notes or "ответ корректен и подкреплён цитированными клозами",
            "missed_norms": [],
        }
        prompt = (
            f"[SYSTEM]\n{REVIEWER_SYSTEM}\n\n"
            f"[USER]\nВОПРОС:\n{row['question']}\n\n"
            f"ОТВЕТ ПЕРВОГО ЭКСПЕРТА:\n{analyst}\n\n"
            f"КЛОЗЫ ИЗ БАЗЫ НТД:\n{format_user_prompt(row).split('КЛОЗЫ ИЗ БАЗЫ НТД:', 1)[-1].strip()}"
        )
        yield {
            "prompt": prompt,
            "chosen": json.dumps(good_verdict, ensure_ascii=False),
            "rejected": json.dumps(reviewer_raw, ensure_ascii=False),
            "metadata": {
                "log_id": row["id"],
                "final_decision": "claude_was_right",
                "disagreement": True,
                "reviewer_verdict": row.get("reviewer_verdict"),
                "expert_verdict": row.get("expert_verdict"),
                "analyst_model": row.get("analyst_model"),
                "reviewer_model": row.get("reviewer_model"),
                "k_used": row.get("k_used"),
                "role": "critic",
            },
        }


def write_jsonl(path: Path, items: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--format", choices=["sft", "dpo", "both"], default="both")
    p.add_argument("--output", default="out/pretrain", help="каталог для JSONL")
    p.add_argument("--min-cases", type=int, default=0,
                   help="минимум размеченных строк; иначе exit code 3")
    p.add_argument("--tag", default=None, help="суффикс для имён файлов (по умолчанию — дата)")
    args = p.parse_args()

    total = count_labeled()
    print(f"📦 Размеченных строк в ntd.cross_validation_labeled: {total}")
    if total < args.min_cases:
        print(f"⚠️  Меньше порога ({args.min_cases}). Прерываюсь.")
        return 3

    out_dir = Path(args.output)
    tag = args.tag or datetime.now(timezone.utc).strftime("%Y%m%d")
    written = {}
    by_final: dict[str, int] = {}
    by_expert: dict[str, int] = {}

    def streamed_rows() -> Iterable[dict]:
        """Один проход по курсору; попутно агрегируем bucket-статистику."""
        for r in iter_labeled():
            f = r.get("final_decision") or "null"
            by_final[f] = by_final.get(f, 0) + 1
            e = r.get("expert_verdict") or "null"
            by_expert[e] = by_expert.get(e, 0) + 1
            yield r

    if args.format == "both":
        # Не материализуем — гоняем курсор по разу на каждый формат, чтобы
        # остаться O(1) по памяти. bucket-счётчики собираем только на первом
        # проходе через streamed_rows().
        sft_path = out_dir / f"ntd_sft_{tag}.jsonl"
        written["sft"] = (sft_path, write_jsonl(sft_path, to_sft(streamed_rows())))
        dpo_path = out_dir / f"ntd_dpo_{tag}.jsonl"
        written["dpo"] = (dpo_path, write_jsonl(dpo_path, to_dpo(iter_labeled())))
        dpo_critic_path = out_dir / f"ntd_dpo_critic_{tag}.jsonl"
        written["dpo_critic"] = (
            dpo_critic_path,
            write_jsonl(dpo_critic_path, to_dpo_critic(iter_labeled())),
        )
    elif args.format == "sft":
        sft_path = out_dir / f"ntd_sft_{tag}.jsonl"
        written["sft"] = (sft_path, write_jsonl(sft_path, to_sft(streamed_rows())))
    elif args.format == "dpo":
        dpo_path = out_dir / f"ntd_dpo_{tag}.jsonl"
        written["dpo"] = (dpo_path, write_jsonl(dpo_path, to_dpo(streamed_rows())))
        # Симметричный поток для критика: claude_was_right + disagreement.
        dpo_critic_path = out_dir / f"ntd_dpo_critic_{tag}.jsonl"
        written["dpo_critic"] = (
            dpo_critic_path,
            write_jsonl(dpo_critic_path, to_dpo_critic(iter_labeled())),
        )

    for k, (path, n) in written.items():
        print(f"   {k.upper():4s}  {n:>4d} примеров  →  {path}")

    summary_path = out_dir / f"summary_{tag}.json"
    summary_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_labeled": total,
        "outputs": {k: {"path": str(v[0]), "count": v[1]} for k, v in written.items()},
        "by_final_decision": by_final,
        "by_expert_verdict": by_expert,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   META  →  {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
