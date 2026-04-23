"""Экспорт итоговой Выписки ИРД (пакет документов) в DOCX."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from .classifier import SECTION_LABELS


def export_batch_docx(
    items: list[dict[str, Any]],
    output_path: str,
    project_name: str = "",
) -> None:
    """Формирует DOCX «Выписка ИРД» из пакета классифицированных документов.

    items: список dict от classifier.process_document(), дополненных полями:
        source_file (str), formatted_text (может быть отредактирован пользователем)
    """
    doc = Document()

    # --- Поля страницы ---
    sec = doc.sections[0]
    sec.top_margin = Cm(2)
    sec.bottom_margin = Cm(2)
    sec.left_margin = Cm(3)
    sec.right_margin = Cm(1.5)

    _set_normal_font(doc)

    # --- Заголовок ---
    h = doc.add_heading("ВЫПИСКА ИРД", level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _style_heading(h, size=14, bold=True)

    if project_name:
        sub = doc.add_paragraph(project_name)
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.runs[0].italic = True

    meta = doc.add_paragraph(f"Дата формирования: {datetime.now().strftime('%d.%m.%Y')}")
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    meta.runs[0].font.size = Pt(9)
    meta.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    doc.add_paragraph()  # отступ

    # --- Группируем по разделам ---
    sections_order = ["main", "tech_conditions", "approvals"]
    grouped: dict[str, list[dict]] = {s: [] for s in sections_order}
    unknown = []

    for item in items:
        section = item.get("section", "")
        if section in grouped:
            grouped[section].append(item)
        else:
            unknown.append(item)

    counters: dict[str, int] = {}  # сквозная нумерация внутри каждого раздела

    for section_key in sections_order:
        section_items = grouped[section_key]
        if not section_items:
            continue

        # заголовок раздела
        sh = doc.add_heading(SECTION_LABELS.get(section_key, section_key), level=2)
        _style_heading(sh, size=12, bold=True)

        # нумерованный список
        counters[section_key] = 0
        for item in section_items:
            counters[section_key] += 1
            text = item.get("formatted_text", "").strip()
            confidence = item.get("confidence", 1.0)
            source = Path(item.get("source_file", "")).name

            p = doc.add_paragraph(style="List Number")
            run = p.add_run(text)
            run.font.size = Pt(11)

            # помечаем неуверенные записи
            if confidence < 0.4:
                run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
                note_run = p.add_run(f"  [требует проверки, источник: {source}]")
                note_run.font.size = Pt(9)
                note_run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
                note_run.italic = True
            elif source:
                note_run = p.add_run(f"  [{source}]")
                note_run.font.size = Pt(9)
                note_run.font.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)
                note_run.italic = True

        doc.add_paragraph()  # отступ между разделами

    # --- Нераспознанные ---
    if unknown:
        sh = doc.add_heading("Не определены", level=2)
        _style_heading(sh, size=12, bold=True)
        for item in unknown:
            p = doc.add_paragraph(style="List Number")
            run = p.add_run(item.get("formatted_text", "[нет данных]"))
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def _set_normal_font(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)


def _style_heading(heading, size: int, bold: bool) -> None:
    for run in heading.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
