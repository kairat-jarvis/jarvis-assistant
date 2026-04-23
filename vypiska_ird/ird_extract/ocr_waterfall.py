"""Трёхуровневый waterfall извлечения текста из PDF.

Строгий порядок уровней (пропускать нельзя):
    1. pdfplumber          — текстовый слой PDF
    2. PaddleOCR-VL-1.5    — единственный допустимый OCR-движок
    3. Claude Vision       — fallback, только если уровень 2 не справился

Запрещённые движки: tesseract, easyocr, doctr, surya, PaddleOCR < 1.5.

Каждый переход на уровень 3 логируется в Supabase.jarvis_agent_logs
с причиной эскалации (низкая уверенность PaddleOCR, ошибка, пустой результат).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pdfplumber
from pdf2image import convert_from_path
from PIL import Image

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация (через переменные окружения)
# ---------------------------------------------------------------------------

# Порог "достаточно текста на странице" — ниже него страница считается сканом
MIN_TEXT_LEN = int(os.environ.get("WATERFALL_MIN_TEXT_LEN", "50"))

# Порог уверенности PaddleOCR: ниже — эскалация на Claude Vision
PADDLE_CONF_THRESHOLD = float(os.environ.get("PADDLE_CONF_THRESHOLD", "0.6"))

# Язык и модель для PaddleOCR-VL
PADDLE_LANG = os.environ.get("PADDLE_LANG", "ru")
PADDLE_VL_MODEL = os.environ.get("PADDLE_VL_MODEL", "PaddleOCR-VL-1.5")

# Claude Vision модель для fallback
CLAUDE_VISION_MODEL = os.environ.get("CLAUDE_VISION_MODEL", "claude-sonnet-4-6")

TIER_PDFPLUMBER = "pdfplumber"
TIER_PADDLE = "paddleocr-vl-1.5"
TIER_CLAUDE = "claude-vision"


@dataclass
class PageResult:
    text: str
    tier: str            # какой уровень дал финальный результат
    confidence: float    # [0.0 .. 1.0]
    fallback_reason: Optional[str] = None  # заполняется только при tier=claude-vision


# ---------------------------------------------------------------------------
# Уровень 1 — pdfplumber
# ---------------------------------------------------------------------------

def _try_pdfplumber(page) -> tuple[str, float]:
    """Извлекает текстовый слой через pdfplumber.

    Возвращает (text, confidence). confidence = 1.0, если длина >= MIN_TEXT_LEN,
    иначе 0.0 — сигнал эскалации на уровень 2.
    """
    try:
        text = (page.extract_text() or "").strip()
    except Exception as exc:  # pdfplumber иногда падает на битых PDF
        log.warning("pdfplumber extract_text failed: %s", exc)
        return "", 0.0

    if len(text) >= MIN_TEXT_LEN:
        return text, 1.0
    return text, 0.0


# ---------------------------------------------------------------------------
# Уровень 2 — PaddleOCR-VL-1.5
# ---------------------------------------------------------------------------

_paddle_instance = None
_paddle_import_error: Optional[str] = None


def _get_paddle():
    """Ленивая инициализация PaddleOCR-VL. Кэшируется на процесс."""
    global _paddle_instance, _paddle_import_error
    if _paddle_instance is not None:
        return _paddle_instance
    if _paddle_import_error is not None:
        return None

    try:
        from paddleocr import PaddleOCR  # type: ignore
    except ImportError as exc:
        _paddle_import_error = (
            f"PaddleOCR не установлен ({exc}). "
            "Установите: pip install 'paddleocr>=3.1' paddlepaddle. "
            "Альтернативные OCR (tesseract/easyocr/doctr/surya) запрещены политикой проекта."
        )
        log.error(_paddle_import_error)
        return None

    try:
        _paddle_instance = PaddleOCR(
            lang=PADDLE_LANG,
            use_doc_orientation_classify=True,
            use_textline_orientation=True,
            ocr_version=PADDLE_VL_MODEL,
        )
    except TypeError:
        # Старая сигнатура без ocr_version — PaddleOCR < 3.1 недопустим
        _paddle_import_error = (
            f"Обнаружена устаревшая версия paddleocr (не поддерживает ocr_version=). "
            f"Обновите до >=3.1 для {PADDLE_VL_MODEL}."
        )
        log.error(_paddle_import_error)
        return None
    except Exception as exc:
        _paddle_import_error = f"PaddleOCR инициализация провалена: {exc}"
        log.error(_paddle_import_error)
        return None

    return _paddle_instance


def _try_paddle(image: Image.Image) -> tuple[str, float]:
    """OCR через PaddleOCR-VL-1.5.

    Возвращает (text, avg_confidence). avg_confidence=0.0 при ошибке/пустом результате.
    """
    ocr = _get_paddle()
    if ocr is None:
        return "", 0.0

    try:
        import numpy as np  # PaddleOCR принимает ndarray
        arr = np.array(image.convert("RGB"))
        result = ocr.predict(arr)
    except Exception as exc:
        log.warning("PaddleOCR предикт упал: %s", exc)
        return "", 0.0

    # Результат PaddleOCR 3.x: list[dict] с rec_texts и rec_scores
    texts: list[str] = []
    scores: list[float] = []
    try:
        for page in result or []:
            rec_texts = page.get("rec_texts") or []
            rec_scores = page.get("rec_scores") or []
            for t, s in zip(rec_texts, rec_scores):
                if t:
                    texts.append(str(t))
                    scores.append(float(s))
    except AttributeError:
        # Совсем старый API — результат как list[list[ [box, (text, score)] ]]
        for page in result or []:
            for line in page or []:
                try:
                    _, (t, s) = line[0], line[1]
                    texts.append(str(t))
                    scores.append(float(s))
                except (IndexError, TypeError, ValueError):
                    continue

    if not texts:
        return "", 0.0

    avg_conf = sum(scores) / len(scores) if scores else 0.0
    return "\n".join(texts), avg_conf


# ---------------------------------------------------------------------------
# Уровень 3 — Claude Vision (fallback only)
# ---------------------------------------------------------------------------

_claude_client = None


def _get_claude():
    global _claude_client
    if _claude_client is not None:
        return _claude_client
    try:
        import anthropic  # type: ignore
    except ImportError:
        log.error("anthropic SDK не установлен — уровень 3 waterfall недоступен")
        return None
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.error("ANTHROPIC_API_KEY не задан — Claude Vision fallback недоступен")
        return None
    _claude_client = anthropic.Anthropic(api_key=key)
    return _claude_client


def _try_claude_vision(image: Image.Image) -> tuple[str, float]:
    """Fallback-OCR через Claude Vision. Вызывать только после провала уровня 2."""
    client = _get_claude()
    if client is None:
        return "", 0.0

    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")

    try:
        msg = client.messages.create(
            model=CLAUDE_VISION_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Извлеки весь видимый текст со страницы. "
                                "Сохрани порядок чтения и структуру (заголовки, списки, абзацы). "
                                "Не добавляй комментариев, не переводи — только чистый текст."
                            ),
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        log.error("Claude Vision API error: %s", exc)
        return "", 0.0

    parts = [block.text for block in msg.content if getattr(block, "type", None) == "text"]
    text = "\n".join(parts).strip()
    # confidence для Claude Vision не измеряем — используем 0.9 как условный индикатор
    return text, 0.9 if text else 0.0


# ---------------------------------------------------------------------------
# Логирование эскалаций в Supabase
# ---------------------------------------------------------------------------

def _log_claude_fallback(pdf_name: str, page_num: int, reason: str, metrics: dict) -> None:
    """Пишет запись в jarvis_agent_logs при срабатывании уровня 3.

    Для работы нужны SUPABASE_URL и SUPABASE_SERVICE_KEY. Если их нет — пишем
    в локальный файл логов (чтобы эскалации никогда не терялись молча).
    """
    payload = {
        "agent": "ocr_waterfall",
        "action": "claude_vision_fallback",
        "status": "fallback",
        "details": {
            "pdf": pdf_name,
            "page": page_num,
            "reason": reason,
            "metrics": metrics,
            "tier": TIER_CLAUDE,
        },
    }

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

    if url and key:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{url.rstrip('/')}/rest/v1/jarvis_agent_logs",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return
                log.warning("jarvis_agent_logs HTTP %s", resp.status)
        except Exception as exc:
            log.warning("Supabase log failed: %s", exc)

    # Фолбэк — локальный jsonl
    local = Path(os.environ.get("WATERFALL_LOG_PATH") or "waterfall_fallbacks.jsonl")
    try:
        with local.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), **payload}, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.error("Локальный лог waterfall не удалось записать: %s", exc)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def extract_page(
    page,                     # pdfplumber.page.Page
    pdf_path: str,
    page_num: int,
    dpi: int = 300,
    poppler_path: Optional[str] = None,
) -> PageResult:
    """Прогоняет одну страницу через waterfall в строгом порядке.

    Уровни переключаются только сверху вниз. Пропуск уровней недопустим.
    """
    pdf_name = Path(pdf_path).name

    # --- Уровень 1: pdfplumber -------------------------------------------------
    text, conf = _try_pdfplumber(page)
    if conf >= 1.0:
        return PageResult(text=text, tier=TIER_PDFPLUMBER, confidence=conf)

    # --- Рендер страницы для уровней 2+ ----------------------------------------
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=dpi,
            poppler_path=poppler_path,
        )
        image = images[0] if images else None
    except Exception as exc:
        log.error("pdf2image rendering failed: %s", exc)
        image = None

    if image is None:
        return PageResult(text=text, tier=TIER_PDFPLUMBER, confidence=0.0)

    # --- Уровень 2: PaddleOCR-VL-1.5 ------------------------------------------
    paddle_text, paddle_conf = _try_paddle(image)
    paddle_len = len(paddle_text.strip())

    if paddle_conf >= PADDLE_CONF_THRESHOLD and paddle_len >= MIN_TEXT_LEN:
        return PageResult(text=paddle_text, tier=TIER_PADDLE, confidence=paddle_conf)

    # --- Уровень 3: Claude Vision (fallback only) -----------------------------
    if paddle_len < MIN_TEXT_LEN and paddle_conf == 0.0:
        reason = "paddle_failed_or_empty"
    elif paddle_conf < PADDLE_CONF_THRESHOLD:
        reason = f"paddle_low_confidence({paddle_conf:.2f}<{PADDLE_CONF_THRESHOLD})"
    else:
        reason = "paddle_insufficient_text"

    metrics = {
        "paddle_confidence": round(paddle_conf, 3),
        "paddle_text_len": paddle_len,
        "pdfplumber_text_len": len(text),
        "threshold": PADDLE_CONF_THRESHOLD,
    }
    _log_claude_fallback(pdf_name, page_num, reason, metrics)

    claude_text, claude_conf = _try_claude_vision(image)
    # Если Claude тоже не справился — возвращаем лучший из доступных как есть
    if not claude_text:
        best_text = paddle_text or text
        best_tier = TIER_PADDLE if paddle_text else TIER_PDFPLUMBER
        return PageResult(
            text=best_text,
            tier=best_tier,
            confidence=paddle_conf,
            fallback_reason=f"{reason};claude_vision_failed",
        )

    return PageResult(
        text=claude_text,
        tier=TIER_CLAUDE,
        confidence=claude_conf,
        fallback_reason=reason,
    )


def extract_pdf(
    pdf_path: str,
    dpi: int = 300,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[str, list[PageResult]]:
    """Прогоняет весь PDF через waterfall.

    Возвращает (full_text, per_page_results). Каждая страница имеет
    собственный tier — PDF может быть смешанным (часть текстовых, часть сканов).
    """
    poppler_path = os.environ.get("POPPLER_PATH") or None
    parts: list[str] = []
    results: list[PageResult] = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for idx, page in enumerate(pdf.pages, start=1):
            if progress:
                progress(idx, total, f"Страница {idx}/{total}: waterfall L1")

            res = extract_page(page, pdf_path, idx, dpi=dpi, poppler_path=poppler_path)

            if progress and res.tier != TIER_PDFPLUMBER:
                progress(idx, total, f"Страница {idx}/{total}: {res.tier}")

            parts.append(f"--- стр. {idx} ({res.tier}) ---\n{res.text}")
            results.append(res)

    return "\n\n".join(parts), results
