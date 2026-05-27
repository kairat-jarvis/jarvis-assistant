#!/usr/bin/env python3
"""
Stop hook auto-capture (Режим C).
Парсит транскрипт завершившейся сессии, извлекает high-confidence маркеры
(явные просьбы запомнить, решения, задачи) и сохраняет в jarvis_memory.

Input stdin: {"session_id": "...", "stop_reason": "..."}
Запускается async — не блокирует сессию.
Логирует в ~/.claude/auto_capture.log для отладки.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path("/Users/kairat/Claude Code/JARVIS ASSISTANT")
sys.path.insert(0, str(PROJECT_ROOT))

LOG_FILE = Path.home() / ".claude" / "auto_capture.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("auto_capture")

# ── Регулярки-маркеры ──────────────────────────────────────────────────────
# Порог confidence 0.8: только явные, однозначные маркеры
EXPLICIT_SAVE_RE = re.compile(
    r"(запомни|зафиксируй|сохрани в памят|jarvis запиши|jarvis,? запомни"
    r"|remember this|save this|note this down)",
    re.I,
)
DECISION_RE = re.compile(
    r"(решение:|принято решение:|договорились:|итак,? решили|будем делать так"
    r"|we decided|decision:|agreed:)",
    re.I,
)
TASK_RE = re.compile(
    r"^(задача:|todo:|нужно сделать:|action item:|followup:|follow-up:)",
    re.I | re.MULTILINE,
)

MIN_SESSION_EXCHANGES = 3   # меньше — слишком короткая, не сохраняем
MAX_TRANSCRIPT_LINES = 500  # читаем только хвост (экономим память)


def find_transcript(session_id: str) -> Path | None:
    """Ищет JSONL транскрипт по session_id в ~/.claude/projects/*/."""
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None
    # Быстрый поиск: имя файла == session_id.jsonl
    for f in projects_dir.rglob(f"{session_id}.jsonl"):
        if f.is_file():
            return f
    return None


def parse_transcript(path: Path) -> list[dict]:
    """Читает последние MAX_TRANSCRIPT_LINES строк и возвращает только user/assistant."""
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
                # извлекаем текстовые блоки
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
        log.warning("parse_transcript failed: %s", exc)
    return messages


def extract_candidates(messages: list[dict]) -> list[dict]:
    """
    Возвращает список кандидатов на сохранение.
    Каждый: {"content_type", "content", "summary", "confidence", "tags"}
    """
    candidates = []

    for i, msg in enumerate(messages):
        text = msg["text"]

        # 1. Явная просьба запомнить (confidence 0.95)
        if msg["role"] == "user" and EXPLICIT_SAVE_RE.search(text):
            # Берём следующее сообщение ассистента как content если оно есть
            ctx = messages[i + 1]["text"] if i + 1 < len(messages) else text
            candidates.append({
                "content_type": "note",
                "content": ctx[:1000],
                "summary": text[:150],
                "confidence": 0.95,
                "tags": ["auto-captured", "explicit-save"],
            })

        # 2. Маркер решения (confidence 0.88)
        m = DECISION_RE.search(text)
        if m:
            # Извлекаем предложение после маркера
            after = text[m.end():].strip()
            snippet = after.split("\n")[0][:300]
            if len(snippet) > 20:
                candidates.append({
                    "content_type": "decision",
                    "content": text[:800],
                    "summary": snippet,
                    "confidence": 0.88,
                    "tags": ["auto-captured", "decision"],
                })

        # 3. Маркер задачи (confidence 0.82)
        if TASK_RE.search(text):
            lines_with_task = [
                l.strip() for l in text.splitlines()
                if TASK_RE.match(l.strip())
            ]
            for task_line in lines_with_task[:3]:
                if len(task_line) > 15:
                    candidates.append({
                        "content_type": "task",
                        "content": task_line[:300],
                        "summary": task_line[:150],
                        "confidence": 0.82,
                        "tags": ["auto-captured", "task"],
                    })

    return candidates


def run(session_id: str) -> int:
    transcript_path = find_transcript(session_id)
    if not transcript_path:
        log.info("Transcript not found for session %s", session_id)
        return 0

    messages = parse_transcript(transcript_path)
    user_count = sum(1 for m in messages if m["role"] == "user")
    if user_count < MIN_SESSION_EXCHANGES:
        log.info("Session %s too short (%d user msgs), skipping", session_id, user_count)
        return 0

    candidates = extract_candidates(messages)
    if not candidates:
        log.info("Session %s: no high-confidence candidates", session_id)
        return 0

    # Импортируем здесь чтобы не падать при отсутствии зависимостей
    try:
        from scripts.jarvis_local import JarvisLocal  # noqa: E402
        cli = JarvisLocal()
    except Exception as exc:
        log.error("JarvisLocal import failed: %s", exc)
        return 1

    saved = 0
    for c in candidates:
        if c["confidence"] < 0.8:
            continue
        try:
            mid = cli.add_memory(
                content=c["content"],
                content_type=c["content_type"],
                summary=c["summary"],
                tags=c["tags"],
                priority="medium",
                source="auto_capture_stop_hook",
                metadata={
                    "session_id": session_id,
                    "session_date": date.today().isoformat(),
                    "confidence": c["confidence"],
                    "auto_captured": True,
                    "transcript_path": str(transcript_path),
                },
            )
            cli.log_action(
                agent_id="jarvis-memory-curator",
                action="auto_capture",
                input_data={"session_id": session_id, "content_type": c["content_type"]},
                output_data={"memory_id": mid, "confidence": c["confidence"]},
                status="success",
            )
            saved += 1
            log.info("Saved %s (confidence=%.2f) id=%s", c["content_type"], c["confidence"], mid)
        except Exception as exc:
            log.error("Failed to save candidate: %s", exc)

    log.info("Session %s: saved %d/%d candidates", session_id, saved, len(candidates))
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    session_id = data.get("session_id", "")
    if not session_id:
        log.warning("No session_id in hook input: %s", raw[:200] if raw else "empty")
        return 0

    try:
        return run(session_id)
    except Exception as exc:
        log.error("Unhandled exception: %s", exc, exc_info=True)
        return 0  # не блокируем Stop


if __name__ == "__main__":
    sys.exit(main())
