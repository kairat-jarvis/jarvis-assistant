"""ntd_ask_with_review.py — тестовый запрос по нормам с независимым ревью.

Поток:
1. Берём вопрос (CLI-аргумент или дефолт).
2. Считаем эмбеддинг text-embedding-3-small.
3. hybrid_search_clauses в локальной expertise_ntd → top-K релевантных клозов.
4. Просим Claude (Sonnet) дать ответ по нормам со ссылками на эти клозы.
5. Передаём вопрос + ответ + контекст независимому эксперту (OpenAI),
   модель из VERIFIER_MODEL (по умолчанию gpt-5 → o4-mini fallback),
   принцип как в expertise-orchestrator/scripts/re-verify.ts.
6. Печатаем оба вердикта рядом.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Json

sys.path.insert(0, str(Path(__file__).parent))
from ntd_local import NtdLocal

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

NTD_PG_URL = os.getenv("NTD_PG_URL", "postgresql://localhost/expertise_ntd")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "gpt-5")
ANALYST_MODEL = os.getenv("ANALYST_MODEL", "claude-sonnet-4-5-20250929")

EMBED_MODEL = "text-embedding-3-small"

ANALYST_SYSTEM = """Ты — главный эксперт государственной экспертизы РК по разделам АПС/СОУЭ.
Тебе дан вопрос и список потенциально релевантных клозов из локальной базы НТД.
Правила:
1. Отвечай строго по этим клозам. Цитируй doc_code и пункт.
2. НЕ экстраполируй условие из одного клоза на параметры из другого
   (если клоз ограничен высотой 50 м — он не применяется к зданию 75 м).
3. Если клозы не отвечают на вопрос — прямо скажи «нет данных в базе».
4. В конце укажи confidence: high|medium|low."""

REVIEWER_SYSTEM = """Ты — независимый эксперт государственной экспертизы проектной документации
строительства Республики Казахстан. Тебе дан вопрос инженера и ответ другого эксперта
со ссылками на клозы НТД. Выдай вердикт:
- confirmed: ответ корректен и подкреплён клозами
- rejected: ответ противоречит нормам или искажает их
- uncertain: данных недостаточно для оценки

Ответ строго в JSON:
{"verdict": "confirmed|rejected|uncertain",
 "rationale": "одно-два предложения, что именно подтверждаешь/опровергаешь",
 "missed_norms": ["перечень норм/пунктов, которые стоило бы привлечь, или пустой массив"]}"""


def embed_query(text: str) -> list[float]:
    from openai import OpenAI
    cli = OpenAI(api_key=OPENAI_KEY)
    r = cli.embeddings.create(model=EMBED_MODEL, input=text)
    return r.data[0].embedding


def search_ntd(question: str, k: int = 8) -> list[dict]:
    emb = embed_query(question)
    ntd = NtdLocal()
    return ntd.hybrid_search(query_text=question, query_embedding=emb, match_count=k)


def format_context(clauses: list[dict]) -> str:
    out = []
    for i, c in enumerate(clauses, 1):
        meta = c.get("metadata") or {}
        doc = meta.get("doc_code") or "НТД"
        clause = meta.get("clause_no") or meta.get("clause") or meta.get("number") or ""
        content = (c.get("content") or "").strip().replace("\n", " ")
        out.append(f"[{i}] {doc} п.{clause}\n{content[:800]}")
    return "\n\n".join(out)


class AnalystError(RuntimeError):
    """Сбой вызова аналитика — пробрасываем наружу, чтобы main() мог
    залогировать структурированную ошибку и выйти с ненулевым кодом."""


def ask_analyst(question: str, context: str) -> str:
    import anthropic
    cli = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        msg = cli.messages.create(
            model=ANALYST_MODEL,
            max_tokens=1500,
            system=ANALYST_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"ВОПРОС:\n{question}\n\nКЛОЗЫ ИЗ БАЗЫ НТД:\n{context}",
            }],
        )
    except anthropic.APIStatusError as e:
        raise AnalystError(f"anthropic APIStatusError: status={e.status_code} message={e}") from e
    except anthropic.APIConnectionError as e:
        raise AnalystError(f"anthropic APIConnectionError: {e}") from e
    except anthropic.APITimeoutError as e:
        raise AnalystError(f"anthropic APITimeoutError: {e}") from e
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def review_with_openai(question: str, analyst_answer: str, context: str) -> dict:
    from openai import OpenAI
    cli = OpenAI(api_key=OPENAI_KEY)
    # Контекст не режем: аналитик видит полный список клозов, ревьюер должен
    # получать тот же payload, иначе будет ложный disagreement из-за того, что
    # «нужного пункта нет в его инпуте» — это засоряет SFT/DPO мусором.
    payload = (
        f"ВОПРОС:\n{question}\n\n"
        f"ОТВЕТ ПЕРВОГО ЭКСПЕРТА:\n{analyst_answer}\n\n"
        f"ВЫЖИМКА ИЗ БАЗЫ НТД (доступная обоим):\n{context}"
    )
    try:
        resp = cli.chat.completions.create(
            model=VERIFIER_MODEL,
            messages=[
                {"role": "system", "content": REVIEWER_SYSTEM},
                {"role": "user", "content": payload},
            ],
            response_format={"type": "json_object"},
        )
        if not getattr(resp, "choices", None):
            return {"verdict": "error", "rationale": "empty response (no choices)", "missed_norms": []}
        msg = resp.choices[0].message
        # Новые модели в JSON-mode (gpt-5/gpt-4.1) кладут разобранный объект в
        # message.parsed — если он есть и не пуст, доверяем ему: SDK сам провёл
        # json.loads и валидацию схемы.
        parsed = getattr(msg, "parsed", None)
        if isinstance(parsed, dict) and parsed:
            return parsed
        content = getattr(msg, "content", None)
        if content is None:
            finish = getattr(resp.choices[0], "finish_reason", None)
            return {
                "verdict": "error",
                "rationale": f"empty message content (finish_reason={finish})",
                "missed_norms": [],
            }
        # Новые модели через response_format могут вернуть content списком частей.
        if isinstance(content, list):
            content = "".join(
                getattr(p, "text", "") or (p.get("text", "") if isinstance(p, dict) else "")
                for p in content
            )
        try:
            return json.loads(content or "{}")
        except json.JSONDecodeError as e:
            return {
                "verdict": "error",
                "rationale": f"reviewer returned non-JSON: {e}",
                "missed_norms": [],
                "raw_text": (content or "")[:2000],
            }
    except Exception as e:
        return {"verdict": "error", "rationale": str(e), "missed_norms": []}


CONFIDENCE_RE = re.compile(r"confidence[\s:=\-–—]*([a-zа-я]+)", re.IGNORECASE)


def _extract_confidence(text: str) -> str | None:
    m = CONFIDENCE_RE.search(text or "")
    if not m:
        return None
    val = re.sub(r"[^a-zа-я]", "", m.group(1).lower())
    if not val:
        return None
    mapping = {"высок": "high", "сред": "medium", "низк": "low"}
    for k, v in mapping.items():
        if val.startswith(k):
            return v
    return val if val in {"high", "medium", "low"} else None


def _claim_from_answer(text: str, n: int = 400) -> str:
    """Берём первый смысловой блок ответа аналитика как «утверждение»."""
    body = re.sub(r"^#+.*\n", "", (text or "").strip(), count=1).strip()
    return body[:n]


def log_to_db(
    *,
    question: str,
    clauses: list[dict],
    k_used: int,
    analyst_model: str,
    analyst_answer: str,
    reviewer_model: str,
    reviewer_response: dict,
) -> int | None:
    verdict = (reviewer_response.get("verdict") or "error").lower()
    if verdict not in {"confirmed", "rejected", "uncertain", "error"}:
        verdict = "error"

    raw_norms = reviewer_response.get("missed_norms")
    if isinstance(raw_norms, str):
        missed = [raw_norms] if raw_norms.strip() else []
    elif isinstance(raw_norms, list):
        missed = [str(n) for n in raw_norms if n]
    else:
        missed = []

    row = {
        "question":          question,
        "context_clauses":   Json(clauses or []),
        "k_used":            k_used,
        "embed_model":       EMBED_MODEL,
        "analyst_model":     analyst_model,
        "analyst_answer":    analyst_answer,
        "analyst_confidence": _extract_confidence(analyst_answer),
        "claim":             _claim_from_answer(analyst_answer),
        "claude_reasoning":  analyst_answer,
        "reviewer_model":    reviewer_model,
        "reviewer_verdict":  verdict,
        "gpt5_critique":     reviewer_response.get("rationale") or "",
        "missed_norms":      missed,
        "reviewer_raw":      Json(reviewer_response),
        "disagreement":      verdict != "confirmed",
    }
    sql = """
        INSERT INTO ntd.cross_validation_log
          (question, context_clauses, k_used, embed_model,
           analyst_model, analyst_answer, analyst_confidence,
           claim, claude_reasoning,
           reviewer_model, reviewer_verdict, gpt5_critique, missed_norms, reviewer_raw,
           disagreement)
        VALUES
          (%(question)s, %(context_clauses)s, %(k_used)s, %(embed_model)s,
           %(analyst_model)s, %(analyst_answer)s, %(analyst_confidence)s,
           %(claim)s, %(claude_reasoning)s,
           %(reviewer_model)s, %(reviewer_verdict)s, %(gpt5_critique)s, %(missed_norms)s, %(reviewer_raw)s,
           %(disagreement)s)
        RETURNING id
    """
    try:
        with psycopg.connect(NTD_PG_URL) as conn, conn.cursor() as cur:
            cur.execute(sql, row)
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"   ⚠️  Не удалось залогировать кейс: {e}")
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?", default=(
        "Какое должно быть время эвакуации людей из здания производственного назначения класса Ф5.1 "
        "и как оно зависит от категории помещения по взрывопожарной опасности?"
    ))
    p.add_argument("-k", type=int, default=8)
    p.add_argument("--no-log", action="store_true", help="не писать в ntd.cross_validation_log")
    args = p.parse_args()

    print("=" * 80)
    print(f"❓ ВОПРОС: {args.question}")
    print("=" * 80)

    print("\n🔎 Гибридный поиск в expertise_ntd...")
    clauses = search_ntd(args.question, k=args.k)
    print(f"   найдено клозов: {len(clauses)}")
    ctx = format_context(clauses)
    for ln in ctx.split("\n\n")[:3]:
        print(f"   • {ln.splitlines()[0]}")

    # Если поиск ничего не вернул — LLM звать бессмысленно: ответ заведомо
    # «нет данных в базе» (см. ANALYST_SYSTEM п.3). Экономим вызов и токены,
    # фиксируем кейс в журнале как retrieval-miss для последующего разбора.
    if not clauses:
        print("\n⚠️  Hybrid search вернул 0 клозов — пропускаем LLM-вызовы.")
        answer = "нет данных в базе\nconfidence: low"
        verdict = {
            "verdict": "uncertain",
            "rationale": "retrieval-miss: hybrid_search вернул 0 клозов, оценивать нечего",
            "missed_norms": [],
        }
    else:
        print(f"\n🧠 Ответ аналитика ({ANALYST_MODEL})...\n" + "-" * 80)
        try:
            answer = ask_analyst(args.question, ctx)
        except AnalystError as e:
            print(f"❌ Аналитик упал: {e}")
            if not args.no_log:
                log_to_db(
                    question=args.question,
                    clauses=clauses,
                    k_used=args.k,
                    analyst_model=ANALYST_MODEL,
                    analyst_answer=f"[ANALYST ERROR] {e}",
                    reviewer_model=VERIFIER_MODEL,
                    reviewer_response={
                        "verdict": "error",
                        "rationale": f"analyst failure: {e}",
                        "missed_norms": [],
                    },
                )
            return 5
        print(answer)
        print("-" * 80)

        print(f"\n🔬 Независимое ревью ({VERIFIER_MODEL})...")
        verdict = review_with_openai(args.question, answer, ctx)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))

    if not args.no_log:
        new_id = log_to_db(
            question=args.question,
            clauses=clauses,
            k_used=args.k,
            analyst_model=ANALYST_MODEL,
            analyst_answer=answer,
            reviewer_model=VERIFIER_MODEL,
            reviewer_response=verdict,
        )
        if new_id is None:
            # cron/CI должны видеть провал записи как ненулевой exit — иначе
            # «тихие» пропуски накапливаются незаметно.
            print("\n❌ Запись в cross_validation_log провалилась — exit 4.")
            return 4
        disagree = (verdict.get("verdict") or "").lower() != "confirmed"
        print(f"\n📝 Залогировано: cross_validation_log.id = {new_id}"
              f"  (disagreement={disagree})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
