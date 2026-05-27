#!/usr/bin/env python3
"""
harvest_session.py — Режим B: интерактивный harvest insights из сессии.

Использование:
    python harvest_session.py              # последняя сессия текущего проекта
    python harvest_session.py <session_id> # конкретная сессия по ID
    python harvest_session.py --list       # список последних сессий
    python harvest_session.py --batch      # batch-сохранение (confidence >= 0.7)
    python harvest_session.py --min-conf 0.85 --batch
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path("/Users/kairat/Claude Code/JARVIS ASSISTANT")
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.jarvis_local import JarvisLocal  # noqa: E402

# ── Директории ────────────────────────────────────────────────────────────────
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CURRENT_PROJECT_DIR = PROJECTS_DIR / "-Users-kairat-Claude-Code-JARVIS-ASSISTANT"

MAX_TRANSCRIPT_LINES = 2000  # Режим B читает больше, чем C

# ── Паттерны извлечения ────────────────────────────────────────────────────────
import re

_PATTERNS: dict[str, tuple[re.Pattern, float, str]] = {
    "explicit_save": (
        re.compile(
            r"(запомни|зафиксируй|сохрани в памят|jarvis запиши|jarvis,? запомни"
            r"|remember this|save this|note this down)",
            re.I,
        ),
        0.95,
        "note",
    ),
    "decision": (
        re.compile(
            r"(решение:|принято решение:|договорились:|итак,? решили|будем делать так"
            r"|теперь делаем так|we decided|decision:|agreed:|договорились на)",
            re.I,
        ),
        0.88,
        "decision",
    ),
    "task": (
        re.compile(
            r"^(задача:|todo:|нужно сделать:|action item:|followup:|follow-up:"
            r"|следующий шаг:|next step:)",
            re.I | re.MULTILINE,
        ),
        0.82,
        "task",
    ),
    "idea": (
        re.compile(
            r"(идея:|придумал|концепт:|а что если|что если мы|можно было бы"
            r"|предложение:|idea:|what if we|concept:)",
            re.I,
        ),
        0.75,
        "idea",
    ),
    "context": (
        re.compile(
            r"(контекст:|важно знать:|для справки:|справочно:|background:"
            r"|fyi:|учти,? что|запомни,? что|имей в виду)",
            re.I,
        ),
        0.72,
        "context",
    ),
}

_PRIORITY_RE: dict[str, re.Pattern] = {
    "critical": re.compile(r"\b(критично|критическ|асап|asap|срочно|blocker|blocking)\b", re.I),
    "high":     re.compile(r"\b(важно|важн|приоритет|high priority)\b", re.I),
    "low":      re.compile(r"\b(потом|позже|когда-нибудь|low priority|not urgent)\b", re.I),
}

_TAG_RE: dict[str, re.Pattern] = {
    "jarvis":     re.compile(r"\bjarvis\b", re.I),
    "automation": re.compile(r"\b(автоматизац|automation|n8n|cron|hook)\b", re.I),
    "ntd":        re.compile(r"\b(нтд|ntd|норматив|снип|гост|sp\s*\d+)\b", re.I),
    "ai":         re.compile(r"\b(claude|gpt|llm|openai|embedding|vector)\b", re.I),
    "db":         re.compile(r"\b(postgresql|postgres|supabase|sql)\b", re.I),
    "skill":      re.compile(r"\b(скилл|skill|навык)\b", re.I),
}

# ── ANSI цвета ─────────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
RED = "\033[31m"
GRAY = "\033[90m"

TYPE_CLR = {
    "idea": "\033[35m", "decision": "\033[33m", "task": "\033[34m",
    "note": "\033[36m", "context": "\033[32m",
    "agent_report": "\033[90m", "digest": "\033[90m",
}
PRIO_CLR = {
    "critical": RED, "high": YELLOW, "medium": "\033[37m", "low": GRAY,
}


def _c(clr: str, text: str) -> str:
    return f"{clr}{text}{R}"


# ── Поиск транскриптов ─────────────────────────────────────────────────────────

def find_latest_transcript() -> Optional[Path]:
    if not CURRENT_PROJECT_DIR.exists():
        return None
    files = sorted(CURRENT_PROJECT_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def find_transcript_by_id(session_id: str) -> Optional[Path]:
    if not PROJECTS_DIR.exists():
        return None
    for f in PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        if f.is_file():
            return f
    return None


def list_recent_sessions(n: int = 15) -> list[tuple[str, Path, datetime]]:
    if not CURRENT_PROJECT_DIR.exists():
        return []
    files = sorted(
        CURRENT_PROJECT_DIR.glob("*.jsonl"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:n]
    return [(f.stem, f, datetime.fromtimestamp(f.stat().st_mtime)) for f in files]


# ── Парсинг транскрипта ────────────────────────────────────────────────────────

def parse_transcript(path: Path) -> list[dict]:
    messages = []
    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()[-MAX_TRANSCRIPT_LINES:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = obj.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                )
            else:
                text = str(content)
            if text.strip():
                messages.append({"role": t, "text": text.strip()})
    except Exception as exc:
        print(f"  ⚠ Ошибка чтения транскрипта: {exc}", file=sys.stderr)
    return messages


# ── Извлечение кандидатов ──────────────────────────────────────────────────────

def _guess_priority(text: str) -> str:
    for p, pat in _PRIORITY_RE.items():
        if pat.search(text):
            return p
    return "medium"


def _guess_tags(text: str) -> list[str]:
    return [tag for tag, pat in _TAG_RE.items() if pat.search(text)]


def extract_candidates(messages: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []

    for i, msg in enumerate(messages):
        text = msg["text"]

        for pname, (pat, conf, default_type) in _PATTERNS.items():
            if pname == "task":
                for line in text.splitlines():
                    line = line.strip()
                    if not pat.match(line) or len(line) < 15:
                        continue
                    sig = line[:60].lower()
                    if sig in seen:
                        continue
                    seen.add(sig)
                    out.append(_make_candidate(
                        content_type="task",
                        content=line[:500],
                        summary=line[:150],
                        conf=conf,
                        text=text,
                        role=msg["role"],
                    ))
            else:
                m = pat.search(text)
                if not m:
                    continue

                if pname == "explicit_save":
                    ctx = messages[i + 1]["text"] if i + 1 < len(messages) else text
                    summary = text[:150].replace("\n", " ")
                    content = ctx[:800]
                else:
                    after = text[m.end():].strip()
                    snippet = after.split("\n")[0][:300].strip()
                    if len(snippet) < 15:
                        snippet = text[max(0, m.start() - 20):m.start() + 200].replace("\n", " ").strip()
                    summary = snippet[:150]
                    content = text[:800]

                sig = summary[:60].lower()
                if sig in seen:
                    continue
                seen.add(sig)

                out.append(_make_candidate(
                    content_type=default_type,
                    content=content,
                    summary=summary,
                    conf=conf,
                    text=text,
                    role=msg["role"],
                ))

    return out


def _make_candidate(
    content_type: str, content: str, summary: str,
    conf: float, text: str, role: str,
) -> dict:
    tags = list(set(_guess_tags(text[:400]) + ["auto-harvest"]))
    return {
        "content_type": content_type,
        "content": content,
        "summary": summary,
        "confidence": conf,
        "priority": _guess_priority(text),
        "tags": tags,
        "role": role,
        "excerpt": text[:300],
    }


# ── Отображение ────────────────────────────────────────────────────────────────

def print_overview(candidates: list[dict]) -> None:
    print(f"\n{BOLD}{'═' * 62}{R}")
    print(f"{BOLD}  JARVIS HARVEST — найденные кандидаты{R}")
    print(f"{BOLD}{'═' * 62}{R}")
    print(f"  {'#':>3}  {'Тип':<12} {'Приор':<9} {'Conf':<6}  {'Summary'}")
    print(f"  {'─' * 56}")
    for i, cand in enumerate(candidates, 1):
        tc = TYPE_CLR.get(cand["content_type"], "")
        pc = PRIO_CLR.get(cand["priority"], "")
        s = cand["summary"][:46].replace("\n", " ")
        print(
            f"  {i:>3}  {tc}{cand['content_type']:<12}{R} "
            f"{pc}{cand['priority']:<9}{R} "
            f"{DIM}{cand['confidence']:.0%:<6}{R}  {s}"
        )
    print()


def print_candidate_detail(idx: int, cand: dict, total: int) -> None:
    tc = TYPE_CLR.get(cand["content_type"], "")
    pc = PRIO_CLR.get(cand["priority"], "")
    print(
        f"\n{BOLD}[{idx}/{total}]{R} "
        f"{tc}{cand['content_type'].upper()}{R} "
        f"| conf={DIM}{cand['confidence']:.0%}{R} "
        f"| prio={pc}{cand['priority']}{R} "
        f"| tags={DIM}{cand['tags']}{R}"
    )
    print(f"  {BOLD}Summary:{R} {cand['summary'][:120]}")
    excerpt = cand.get("excerpt", "")
    if excerpt and len(excerpt) > len(cand["summary"]) + 30:
        short = excerpt[:160].replace("\n", " ").strip()
        print(f"  {DIM}Excerpt: {short}...{R}")


# ── Редактирование ─────────────────────────────────────────────────────────────

VALID_TYPES = {"idea", "task", "note", "query", "decision", "context", "agent_report", "digest"}
VALID_PRIORITIES = {"critical", "high", "medium", "low"}


def edit_candidate(cand: dict) -> dict:
    cand = dict(cand)
    print(f"\n  {BOLD}Редактирование{R} (Enter = оставить текущее):")

    new_type = _prompt(f"  content_type [{cand['content_type']}]: ")
    if new_type and new_type in VALID_TYPES:
        cand["content_type"] = new_type

    new_summary = _prompt(f"  summary [{cand['summary'][:60]}]: ")
    if new_summary:
        cand["summary"] = new_summary

    new_prio = _prompt(f"  priority [{cand['priority']}] (critical/high/medium/low): ")
    if new_prio in VALID_PRIORITIES:
        cand["priority"] = new_prio

    cur_tags = ",".join(cand.get("tags", []))
    new_tags = _prompt(f"  tags [{cur_tags}] (через запятую): ")
    if new_tags:
        cand["tags"] = [t.strip() for t in new_tags.split(",") if t.strip()]

    return cand


# ── Интерактивный обзор ────────────────────────────────────────────────────────

def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def interactive_review(candidates: list[dict], session_id: str) -> list[dict]:
    print_overview(candidates)
    print(
        f"  {len(candidates)} кандидатов | сессия {DIM}{session_id[:8]}{R}\n"
        f"  {_c(GREEN, 'y')}=сохранить  {_c(RED, 'n')}=пропустить  "
        f"{_c(YELLOW, 'e')}=редактировать  {_c(BLUE, 'a')}=все сохранить  "
        f"{_c(GRAY, 'q')}=закончить\n"
    )

    confirmed: list[dict] = []

    for i, cand in enumerate(candidates, 1):
        print_candidate_detail(i, cand, len(candidates))

        while True:
            ans = _prompt(f"  → [{BOLD}{i}{R}/{len(candidates)}] (y/n/e/a/q/?) ").lower()

            if ans in ("y", ""):
                confirmed.append(cand)
                print(f"  {_c(GREEN, '✓')} Добавлен")
                break
            elif ans == "n":
                print(f"  {_c(GRAY, '✗')} Пропущен")
                break
            elif ans == "e":
                cand = edit_candidate(cand)
                confirmed.append(cand)
                print(f"  {_c(GREEN, '✓')} Отредактирован и добавлен")
                break
            elif ans == "a":
                remaining = candidates[i - 1:]
                confirmed.extend(remaining)
                print(f"  {_c(GREEN, '✓')} Все оставшиеся ({len(remaining)}) добавлены")
                return confirmed
            elif ans == "q":
                print(f"\n  {_c(YELLOW, '⏹')} Завершено. "
                      f"Отобрано {len(confirmed)} из {i - 1} просмотренных.")
                return confirmed
            elif ans == "?":
                print("  y/Enter — сохранить | n — пропустить | e — редактировать | "
                      "a — все сохранить | q — закончить")
            else:
                print(f"  Неизвестная команда '{ans}'. y/n/e/a/q/?")

    return confirmed


# ── Сохранение ─────────────────────────────────────────────────────────────────

def save_confirmed(
    confirmed: list[dict],
    session_id: str,
    transcript_path: Path,
    *,
    interactive: bool = True,
) -> int:
    cli = JarvisLocal()
    saved = 0

    for cand in confirmed:
        # Анти-дубликат
        existing = cli.fts_only(query_text=cand["summary"], count=3)
        dupes = [r for r in (existing or []) if r.get("fts_score", 0) >= 0.05]
        if dupes:
            print(f"  {_c(YELLOW, '⚠')} Возможный дубликат: {cand['summary'][:60]}")
            for d in dupes:
                s = (d.get("summary") or d.get("content") or "")[:70]
                print(f"      [{d.get('content_type', '?')}] {s}")
            if interactive:
                ans = _prompt("  Всё равно сохранить? (y/N): ").lower()
                if ans != "y":
                    print(f"  {_c(GRAY, '✗')} Пропущен (дубликат)")
                    continue

        try:
            mid = cli.add_memory(
                content=cand["content"],
                content_type=cand["content_type"],
                summary=cand["summary"],
                tags=cand.get("tags", []),
                priority=cand["priority"],
                source="harvest_session",
                metadata={
                    "session_id": session_id,
                    "session_date": date.today().isoformat(),
                    "confidence": cand.get("confidence", 1.0),
                    "auto_captured": False,
                    "harvested": True,
                    "transcript_path": str(transcript_path),
                },
            )
            cli.log_action(
                agent_id="jarvis-memory-curator",
                action="harvest_save",
                input_data={"content_type": cand["content_type"], "tags": cand.get("tags")},
                output_data={"memory_id": mid, "confidence": cand.get("confidence")},
                status="success",
            )
            mid_short = str(mid)[:8]
            print(f"  {_c(GREEN, '✓')} {cand['content_type']} saved "
                  f"(id={mid_short}...)  {cand['summary'][:60]}")
            saved += 1
        except Exception as exc:
            print(f"  {_c(RED, '✗')} Ошибка: {exc}")

    return saved


# ── Точка входа ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="JARVIS harvest_session — интерактивный сбор insights из сессии",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python harvest_session.py               # последняя сессия\n"
            "  python harvest_session.py abc123ef      # конкретная сессия\n"
            "  python harvest_session.py --list        # список сессий\n"
            "  python harvest_session.py --batch       # batch, conf >= 0.7\n"
            "  python harvest_session.py --batch --min-conf 0.85\n"
        ),
    )
    parser.add_argument("session_id", nargs="?", help="Session ID (по умолчанию: последняя)")
    parser.add_argument("--list", "-l", action="store_true", help="Список последних сессий")
    parser.add_argument("--batch", "-b", action="store_true", help="Batch без интерактива")
    parser.add_argument("--min-conf", type=float, default=0.7, metavar="FLOAT",
                        help="Мин. confidence для batch (default: 0.7)")
    args = parser.parse_args()

    # --list
    if args.list:
        sessions = list_recent_sessions()
        if not sessions:
            print("Сессии не найдены в", CURRENT_PROJECT_DIR)
            return 1
        print(f"\n{BOLD}Сессии JARVIS ASSISTANT:{R}")
        for sid, path, mtime in sessions:
            kb = path.stat().st_size // 1024
            print(f"  {mtime.strftime('%Y-%m-%d %H:%M')}  {DIM}{sid[:8]}{R}...  ({kb} KB)")
        return 0

    # Найти транскрипт
    if args.session_id:
        transcript_path = find_transcript_by_id(args.session_id)
        if not transcript_path:
            print(f"Транскрипт не найден: {args.session_id}", file=sys.stderr)
            return 1
        session_id = args.session_id
    else:
        transcript_path = find_latest_transcript()
        if not transcript_path:
            print(f"Нет транскриптов в {CURRENT_PROJECT_DIR}", file=sys.stderr)
            return 1
        session_id = transcript_path.stem

    mtime = datetime.fromtimestamp(transcript_path.stat().st_mtime)
    kb = transcript_path.stat().st_size // 1024
    print(f"\n{BOLD}JARVIS Harvest{R}")
    print(f"  Сессия:  {DIM}{session_id}{R}")
    print(f"  Дата:    {mtime.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Размер:  {kb} KB")

    # Парсинг
    print("\n  Читаю транскрипт...")
    messages = parse_transcript(transcript_path)
    user_count = sum(1 for m in messages if m["role"] == "user")
    print(f"  Найдено сообщений: {len(messages)} ({user_count} от пользователя)")

    if user_count < 2:
        print("  Сессия слишком короткая.")
        return 0

    candidates = extract_candidates(messages)

    if not candidates:
        print(f"\n  {_c(YELLOW, '○')} Кандидатов не обнаружено.")
        print("  Используйте маркеры «решение:», «задача:», «идея:», «запомни» в диалоге.")
        return 0

    # Batch
    if args.batch:
        to_save = [c for c in candidates if c["confidence"] >= args.min_conf]
        print(f"\nBatch: {len(to_save)}/{len(candidates)} кандидатов (conf ≥ {args.min_conf:.0%})")
        saved = save_confirmed(to_save, session_id, transcript_path, interactive=False)
        print(f"\n{_c(GREEN, '✓')} Batch завершён: {saved} сохранено")
        return 0

    # Интерактивный режим
    try:
        confirmed = interactive_review(candidates, session_id)
    except KeyboardInterrupt:
        print(f"\n\n  {_c(YELLOW, '⏹')} Прервано.")
        return 0

    if not confirmed:
        print(f"\n  {DIM}Ничего не выбрано.{R}")
        return 0

    print(f"\n  Сохраняю {len(confirmed)} записей...")
    saved = save_confirmed(confirmed, session_id, transcript_path)
    print(f"\n{_c(GREEN, '✓')} Harvesting завершён: {saved}/{len(confirmed)} сохранено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
