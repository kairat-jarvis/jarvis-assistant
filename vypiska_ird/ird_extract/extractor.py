"""Извлечение текста из PDF через трёхуровневый waterfall.

Порядок (строго сверху вниз, пропуск запрещён):
    1. pdfplumber          — текстовый слой
    2. PaddleOCR-VL-1.5    — единственный OCR-движок
    3. Claude Vision       — fallback только при провале уровня 2

Подробности: см. ocr_waterfall.py.
"""

from __future__ import annotations

from typing import Callable, Optional

from .ocr_waterfall import extract_pdf as _extract_pdf_waterfall


def extract_pdf_text(
    pdf_path: str,
    lang: str = "ru",  # сохранено для обратной совместимости сигнатуры; применяется внутри waterfall
    dpi: int = 300,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """Извлекает текст из PDF через трёхуровневый waterfall.

    Возвращает конкатенированный текст по страницам. Каждая страница
    проходит через waterfall самостоятельно, поэтому смешанные PDF
    (часть с текстовым слоем, часть сканы) обрабатываются корректно.
    """
    text, _results = _extract_pdf_waterfall(pdf_path, dpi=dpi, progress=progress)
    return text
