"""Извлечение текста PDF через Claude PDF API.

Порт `expertise-orchestrator/core/parsers/pdf.ts`:
  • Большие PDF режутся на чанки ≤ TARGET_PAGES_PER_CHUNK стр. / ≤ MAX_PDF_BYTES.
  • Каждый чанк отправляется в Anthropic API как `document` content-block (base64).
  • Claude сам распознаёт текст — никаких pdfplumber / PaddleOCR.

Контракт `extract_pdf(pdf_path) -> (full_text, list[PageResult])` совместим с
прежним вызовом из `loader.py` (где waterfall возвращал тот же тип).
"""
from __future__ import annotations

import base64
import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from anthropic import Anthropic
from pypdf import PdfReader, PdfWriter

log = logging.getLogger("ntd_loader.pdf_extract")

# Лимиты — те же, что в expertise-orchestrator/core/config.ts.
MAX_PDF_BYTES = 28 * 1024 * 1024
MAX_PDF_PAGES = 100
TARGET_PAGES_PER_CHUNK = 40

# Модель: из env CLAUDE_PDF_MODEL, иначе sonnet-4-6 (DEFAULT_MODEL у orchestrator).
DEFAULT_MODEL = os.environ.get("CLAUDE_PDF_MODEL", "claude-sonnet-4-6")
MAX_OUTPUT_TOKENS = int(os.environ.get("CLAUDE_PDF_MAX_TOKENS", "32000"))

TIER_CLAUDE_PDF = "claude-pdf"


@dataclass
class PageResult:
    """Совместим с `ocr_waterfall.PageResult`.

    confidence=1.0 для Claude — модели нет отдельного скоринга на уровне страницы.
    fallback_reason — заполняется, если страница не вошла в чанк (например, > 28 МБ).
    """

    tier: str
    confidence: float
    text: str
    fallback_reason: Optional[str] = None


@dataclass
class _Chunk:
    label: str
    data: bytes
    page_start: int  # 1-based, inclusive
    page_end: int    # 1-based, inclusive


def _chunk_bytes(reader: PdfReader, start: int, end: int) -> bytes:
    """Копирует страницы [start..end) (0-based) в новый PDF и возвращает bytes."""
    writer = PdfWriter()
    for i in range(start, end):
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def load_pdf_chunks(pdf_path: str | os.PathLike[str]) -> list[_Chunk]:
    """Режет PDF на чанки, удовлетворяющие лимитам Anthropic API (≤100 стр., ≤28 МБ)."""
    p = Path(pdf_path)
    raw = p.read_bytes()
    size_mb = len(raw) / 1024 / 1024

    try:
        reader = PdfReader(io.BytesIO(raw))
        total_pages = len(reader.pages)
    except Exception as e:  # noqa: BLE001
        if len(raw) <= MAX_PDF_BYTES:
            log.warning(
                "%s: pypdf не смог разобрать (%s); файл %.1f МБ ≤ %d МБ — шлю как есть.",
                p.name, e, size_mb, MAX_PDF_BYTES // 1024 // 1024,
            )
            return [_Chunk(p.name, raw, 1, 1)]
        raise RuntimeError(
            f'pypdf не смог загрузить "{p.name}" и файл слишком большой '
            f"({size_mb:.1f} МБ): {e}"
        ) from e

    if total_pages == 0:
        raise RuntimeError(f"PDF пустой: {p.name}")

    # Один чанк, если файл небольшой по объёму И по страницам.
    if len(raw) <= MAX_PDF_BYTES and total_pages <= TARGET_PAGES_PER_CHUNK:
        return [_Chunk(p.name, raw, 1, total_pages)]

    log.info(
        "%s: %.1f МБ, %d стр. → режу на чанки (лимиты: %d МБ, %d стр.; цель: %d стр./чанк)",
        p.name, size_mb, total_pages,
        MAX_PDF_BYTES // 1024 // 1024, MAX_PDF_PAGES, TARGET_PAGES_PER_CHUNK,
    )

    avg_bytes_per_page = len(raw) / total_pages
    max_pages_by_size = max(1, int(MAX_PDF_BYTES / avg_bytes_per_page * 0.85))
    target = max(1, min(TARGET_PAGES_PER_CHUNK, MAX_PDF_PAGES - 5, max_pages_by_size))

    chunks: list[_Chunk] = []
    page_start = 0
    while page_start < total_pages:
        chunk_pages = min(target, total_pages - page_start)
        page_end = page_start + chunk_pages
        data = _chunk_bytes(reader, page_start, page_end)

        # Если чанк всё равно тяжёлый — режем вдвое.
        while len(data) > MAX_PDF_BYTES and chunk_pages > 1:
            chunk_pages = chunk_pages // 2
            page_end = page_start + chunk_pages
            data = _chunk_bytes(reader, page_start, page_end)

        # Одиночная страница > 28 МБ — пропускаем (нельзя дробить).
        if len(data) > MAX_PDF_BYTES and chunk_pages == 1:
            log.warning(
                "%s: стр.%d (%.1f МБ) > %d МБ — пропускается. Сожмите PDF.",
                p.name, page_start + 1, len(data) / 1024 / 1024,
                MAX_PDF_BYTES // 1024 // 1024,
            )
            page_start = page_end
            continue

        chunks.append(
            _Chunk(
                label=f"{p.name} [стр.{page_start + 1}–{page_end}]",
                data=data,
                page_start=page_start + 1,
                page_end=page_end,
            )
        )
        page_start = page_end

    total = len(chunks)
    for i, c in enumerate(chunks):
        c.label = c.label.replace("[стр.", f"[ч.{i + 1}/{total} стр.")
    return chunks


_EXTRACTION_PROMPT = (
    "Это страницы нормативно-технического документа (НТД). "
    "Извлеки ПОЛНЫЙ текст всех страниц без пересказа и сокращений.\n\n"
    "Требования к выводу:\n"
    "1. Перед каждой страницей вставь маркер ровно в формате:\n"
    "   --- стр. N (claude-pdf) ---\n"
    "   где N — абсолютный номер страницы в исходном PDF (передан в подсказке).\n"
    "2. Сохраняй ИСХОДНУЮ нумерацию пунктов и подпунктов (1, 1.1, 5.13.2 и т. п.) "
    "в начале строк — это критично для последующего парсинга клозов.\n"
    "3. Заголовки разделов оставляй отдельной строкой.\n"
    "4. Таблицы переводи в текст построчно (строки разделяй переносом).\n"
    "5. Колонтитулы, номера страниц-печати, штампы — НЕ включай в текст.\n"
    "6. Никаких комментариев от тебя; только извлечённый текст."
)


def _extract_chunk_text(client: Anthropic, chunk: _Chunk, model: str) -> str:
    hint = (
        f"Это чанк {chunk.label}. Используй абсолютные номера страниц "
        f"{chunk.page_start}…{chunk.page_end} в маркерах '--- стр. N (claude-pdf) ---'."
    )
    # Anthropic требует streaming для max_tokens, способных занять > 10 мин.
    parts: list[str] = []
    with client.messages.stream(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(chunk.data).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": hint + "\n\n" + _EXTRACTION_PROMPT},
                ],
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            parts.append(text)
    return "".join(parts)


# ─── Page-level split на основе маркеров, который оставила модель ────────────

import re

_PAGE_MARK_RE = re.compile(
    r"^---\s*стр\.\s*(\d+)\s*\((?P<tier>[^)]+)\)\s*---\s*$",
    re.MULTILINE,
)


def _split_pages(full_text: str, *, total_pages: int) -> list[PageResult]:
    """Делит ответ Claude на per-page PageResult по маркерам '--- стр. N (claude-pdf) ---'.

    Если модель пропустила маркеры — отдаём всё одной "страницей" с fallback_reason.
    Если у каких-то страниц вообще нет текста — заполняем заглушками.
    """
    marks = list(_PAGE_MARK_RE.finditer(full_text))
    if not marks:
        return [
            PageResult(
                tier=TIER_CLAUDE_PDF,
                confidence=0.7,
                text=full_text.strip(),
                fallback_reason="модель не вернула page markers",
            )
        ]

    by_page: dict[int, str] = {}
    for i, m in enumerate(marks):
        page_no = int(m.group(1))
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(full_text)
        by_page[page_no] = full_text[start:end].strip()

    results: list[PageResult] = []
    for n in range(1, total_pages + 1):
        text = by_page.get(n, "")
        if text:
            results.append(PageResult(tier=TIER_CLAUDE_PDF, confidence=1.0, text=text))
        else:
            results.append(
                PageResult(
                    tier=TIER_CLAUDE_PDF,
                    confidence=0.0,
                    text="",
                    fallback_reason=f"страница {n} не найдена в ответе модели",
                )
            )
    return results


def extract_pdf(
    pdf_path: str,
    *,
    model: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> tuple[str, list[PageResult]]:
    """Главный API: PDF → (full_text с page-маркерами, список PageResult)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY не задан — нужен для Claude PDF API. "
            "Положите в .env или env, перезапустите."
        )

    model = model or DEFAULT_MODEL
    chunks = load_pdf_chunks(pdf_path)
    # Реальное число страниц для последующего сплита.
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    client = Anthropic()
    parts: list[str] = []
    for c in chunks:
        if progress:
            progress(f"  · {c.label}: запрос к {model}")
        else:
            log.info("extract: %s", c.label)
        text = _extract_chunk_text(client, c, model)
        parts.append(text.strip())

    full_text = "\n\n".join(parts)
    pages = _split_pages(full_text, total_pages=total_pages)
    return full_text, pages
