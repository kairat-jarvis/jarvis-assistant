"""Парсинг текста НТД на отдельные клозы.

Контракт совместим с тем, что уже лежит в expertise_ntd.clause_vectors:
  - content: "Документ: <doc_code>.\nРаздел: <section_path>\nПункт: <clause_no>\nТекст: <body>"
  - metadata: {"doc_code": str, "clause_no": "p.X.Y", "section_top": "X", "section_path": "X > Y"}

Формат clause_no — "p.X.Y" (latin 'p' — так в БД исторически). section_path — "X > Y > Z".

Эвристика разбиения:
  - Заголовки строк вида '^\\s*(\\d+(?:\\.\\d+){0,4})[. ]' — начало клозы.
  - Всё до первого такого маркера — преамбула документа (выкидывается).
  - Текст клозы — от маркера до следующего маркера или конца.
  - Если строка маркера короче 4 символов после номера — считаем её section-заголовком,
    а тело клозы — следующий контент.

Doc_code и doc_title пытаемся вытащить из первых ~3000 символов; если не получается —
требуем явный override через CLI (--doc-code).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

# ─── doc_code parsing ─────────────────────────────────────────────────────────

# Поддерживаемые префиксы документов: СН, СП, СНиП, ВСН, ГОСТ, ОСТ, РД, ПУЭ,
# плюс варианты с " РК" и слитное СНРК/СПРК (исправляется до "СН РК").
_DOC_CODE_RE = re.compile(
    r"\b(?:СНиП|СНРК|СПРК|СН|СП|ВСН|ГОСТ|ОСТ|РД|ПУЭ|НТП)"
    r"(?:\s*РК)?"
    r"\s*"
    r"\d[\d.\-]*\d",
    re.IGNORECASE,
)

_DOC_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

_LATIN_TO_CYRILLIC = str.maketrans({
    "C": "С", "P": "Р", "A": "А", "B": "В", "E": "Е", "H": "Н",
    "K": "К", "M": "М", "O": "О", "T": "Т", "X": "Х", "Y": "У",
})


def normalize_doc_code(s: str) -> str:
    """Приводит doc_code к каноничному виду: latin→cyrillic, 'СНРК'→'СН РК', пробелы."""
    s = s.strip().rstrip(".").translate(_LATIN_TO_CYRILLIC)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\b(СН|СП|СНиП|НТП)РК\b", r"\1 РК", s)
    return s


def detect_doc_code(text: str) -> Optional[str]:
    """Ищет doc_code в первых ~3000 символов (обычно — титульный лист)."""
    head = text[:3000]
    m = _DOC_CODE_RE.search(head)
    return normalize_doc_code(m.group(0)) if m else None


def detect_doc_year(text: str) -> Optional[int]:
    """Берёт первый встретившийся год из шапки документа."""
    head = text[:3000]
    m = _DOC_YEAR_RE.search(head)
    return int(m.group(0)) if m else None


def detect_doc_title(text: str, doc_code: Optional[str]) -> Optional[str]:
    """Заголовок документа — первая длинная строка после doc_code, до 200 символов."""
    head = text[:3000]
    if doc_code:
        idx = head.find(doc_code.split()[0])
        if idx >= 0:
            head = head[idx:]
    for line in head.splitlines():
        line = line.strip()
        # пропускаем сам doc_code и слишком короткие/служебные строки
        if 20 <= len(line) <= 200 and not _DOC_CODE_RE.fullmatch(line):
            return line
    return None


# ─── clause segmentation ──────────────────────────────────────────────────────

# Маркер клозы в начале строки: "1.", "1.1", "5.13.1", "5.13.1." и т.п.
# Допускаем хвост после номера: точка, пробел или конец строки.
_CLAUSE_MARK_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+){0,4})\s*\.?(?:\s+|$)",
    re.MULTILINE,
)

# Внутри страничного разделителя из ocr_waterfall: "--- стр. N (tier) ---"
_PAGE_SEP_RE = re.compile(r"^--- стр\. \d+ \([^)]+\) ---$", re.MULTILINE)


@dataclass
class ParsedClause:
    clause_no: str          # "p.5.13"
    section_path: str       # "5 > 13"
    section_top: str        # "5"
    body: str               # текст клозы (без шапки)


def _strip_page_separators(text: str) -> str:
    """Убирает '--- стр. N (tier) ---' маркеры, оставляя пустую строку для разрыва."""
    return _PAGE_SEP_RE.sub("", text)


def _section_path_from_num(num: str) -> tuple[str, str]:
    """'5.13.1' → ('5 > 13 > 1', '5')."""
    parts = num.split(".")
    return " > ".join(parts), parts[0]


def parse_clauses(text: str, *, min_body_len: int = 30) -> list[ParsedClause]:
    """Сегментирует полный текст PDF на клозы.

    min_body_len отсекает мусорные совпадения вроде "1. " без содержимого.
    Дубли по clause_no убираются — оставляем первое вхождение (так в существующей БД).
    """
    text = _strip_page_separators(text)
    matches = list(_CLAUSE_MARK_RE.finditer(text))
    if not matches:
        return []

    clauses: list[ParsedClause] = []
    seen: set[str] = set()

    for i, m in enumerate(matches):
        num = m.group("num")
        # Тело — от конца маркера до начала следующего (или EOF).
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # Нормализуем пробелы/переносы.
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) < min_body_len:
            continue
        clause_no = f"p.{num}"
        if clause_no in seen:
            continue
        seen.add(clause_no)
        section_path, section_top = _section_path_from_num(num)
        clauses.append(
            ParsedClause(
                clause_no=clause_no,
                section_path=section_path,
                section_top=section_top,
                body=body,
            )
        )
    return clauses


# ─── render content для clause_vectors.content ───────────────────────────────

def render_content(doc_code: str, clause: ParsedClause) -> str:
    """Формирует поле content в том же формате, что уже лежит в БД."""
    return (
        f"Документ: {doc_code}.\n"
        f"Раздел: {clause.section_path}\n"
        f"Пункт: {clause.clause_no}\n"
        f"Текст: {clause.body}"
    )


def iter_clause_payloads(
    doc_code: str, clauses: Iterable[ParsedClause]
) -> Iterable[tuple[str, dict]]:
    """Для каждой клозы возвращает (content, metadata) — то, что пойдёт в clause_vectors."""
    for c in clauses:
        yield render_content(doc_code, c), {
            "doc_code": doc_code,
            "clause_no": c.clause_no,
            "section_top": c.section_top,
            "section_path": c.section_path,
        }
