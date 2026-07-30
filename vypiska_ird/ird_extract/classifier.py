"""Классификация типа ИРД-документа и извлечение реквизитов без LLM.

Подход:
  1. Keyword-scoring по извлечённому тексту → doc_type
  2. Тип-специфичные regex → org_name, date, number, subject
  3. Заполнение шаблона → formatted_text (незнайденные поля → [???])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные регулярки
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS = (
    "январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр"
    "|қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан"
)

_DATE_RE = re.compile(
    r"(?:от\s+)?(\d{1,2})\s+((?:" + _MONTHS + r")\w*)\s+(\d{4})(?:\s*(?:года|жылы|г\.))?",
    re.IGNORECASE,
)
_DATE_NUM_RE = re.compile(r"\b(\d{2})[.\-](\d{2})[.\-](\d{4})\b")
_NUM_RE = re.compile(r"[№#]\s*([А-ЯЁA-Z0-9][А-ЯЁA-Z0-9\-/\.]{1,30})", re.IGNORECASE)
_AREA_RE = re.compile(r"(\d[\d\s]*[,.]?\d*)\s*(?:га|гектар)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")
_KATASTR_RE = re.compile(r"(\d{2}[:\-]\d{3}[:\-]\d{3}[:\-]\d{3,4})")

# Организации: ТОО, АО, ГКП, РГП, КГП, ЗАО, ГП + кавычки
_ORG_SHORT_RE = re.compile(
    r"(?:ТОО|АО|ГКП|РГП|КГП|ЗАО|ГП|ОАО|МКП|КП)\s*«[^»]{2,80}»",
    re.IGNORECASE,
)
# Государственный орган / учреждение (останавливаемся на предлогах и датах)
_ORG_GOV_RE = re.compile(
    r"(?:Управлени[ея]|Отдел|Департамент|Комитет|Министерств|Аким(?:ат)?)\w*"
    r"(?:\s+(?!от\b|для\b|по\b|об?\b|в\b|с\b|и\b|на\b|\d)\w+){0,5}",
    re.IGNORECASE,
)


def _find_date(text: str) -> str:
    """Возвращает 'DD месяц YYYY' — без 'от' и без 'года'."""
    m = _DATE_RE.search(text)
    if m:
        day = f"{int(m.group(1)):02d}"
        month = m.group(2).strip()   # полное слово месяца из текста
        year = m.group(3)
        return f"{day} {month} {year}"
    m = _DATE_NUM_RE.search(text)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "[???]"


def _find_number(text: str) -> str:
    m = _NUM_RE.search(text)
    return m.group(1).strip() if m else "[???]"


def _find_org(text: str) -> str:
    m = _ORG_SHORT_RE.search(text)
    if m:
        return m.group(0).strip()
    m = _ORG_GOV_RE.search(text)
    if m:
        return m.group(0).strip()
    return "[???]"


def _find_area(text: str) -> str:
    m = _AREA_RE.search(text)
    if m:
        val = re.sub(r"\s+", "", m.group(1))
        return val
    return "[???]"


def _find_year(text: str) -> str:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else "[???]"


def _find_cadastral(text: str) -> str:
    m = _KATASTR_RE.search(text)
    return m.group(1) if m else "[???]"


def _first_line(text: str, max_chars: int = 120) -> str:
    """Первая непустая строка текста — суть документа."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:max_chars]
    return "[???]"


# ─────────────────────────────────────────────────────────────────────────────
# Определения типов документов
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocTypeDef:
    key: str
    label: str
    section: str                   # main | tech_conditions | approvals
    keywords: list[str]            # для keyword-scoring (нижний регистр)
    antikeywords: list[str] = field(default_factory=list)
    weight: int = 1                # приоритет при одинаковом score


DOC_TYPES: list[DocTypeDef] = [
    DocTypeDef(
        key="апз", label="АПЗ", section="main",
        keywords=["архитектурно-планировочное задание", "апз", "сәулеттік-жоспарлау тапсырмасы"],
        antikeywords=["задание на проектирование"], weight=3,
    ),
    DocTypeDef(
        key="задание_на_проектирование", label="Задание на проектирование", section="main",
        keywords=["задание на проектирование", "жобалауға тапсырма"],
        weight=2,
    ),
    DocTypeDef(
        key="акт_земля", label="Акт на земельный участок", section="main",
        keywords=["акт на земельный участок", "акт идентификации", "жер учаскесіне акт"],
        weight=3,
    ),
    DocTypeDef(
        key="акт_собственность", label="Акт на право частной собственности", section="main",
        keywords=["акт на право частной собственности", "жеке меншік құқығына акт"],
        weight=3,
    ),
    DocTypeDef(
        key="решение_земля", label="Решение о предоставлении земельного участка", section="main",
        keywords=["о предоставлении", "земельного участка", "жер учаскесін беру туралы", "шешім"],
        antikeywords=["постановление"], weight=2,
    ),
    DocTypeDef(
        key="постановление", label="Постановление акимата", section="main",
        keywords=["постановление", "акимат", "қаулы"],
        weight=2,
    ),
    DocTypeDef(
        key="договор_землепользования", label="Договор землепользования", section="main",
        keywords=["договор", "землепользования", "жерді пайдалану", "жер пайдалану шарты"],
        antikeywords=["купли-продажи", "купля-продажа"], weight=2,
    ),
    DocTypeDef(
        key="договор_купли_продажи", label="Договор купли-продажи", section="main",
        keywords=["договор купли-продажи", "купли продажи", "сату-сатып алу шарты"],
        weight=3,
    ),
    DocTypeDef(
        key="акт_обследования", label="Акт обследования территории", section="main",
        keywords=["акт обследования", "аумақты тексеру актісі"],
        weight=3,
    ),
    DocTypeDef(
        key="дефектная_ведомость", label="Дефектная ведомость", section="main",
        keywords=["дефектная ведомость", "дефектная", "ведомость дефектов"],
        weight=3,
    ),
    DocTypeDef(
        key="перечень_оборудования", label="Перечень оборудования", section="main",
        keywords=["перечень оборудования", "материалов и изделий", "жабдықтар тізімі"],
        weight=3,
    ),
    DocTypeDef(
        key="эскизный_проект", label="Эскизный проект", section="main",
        keywords=["эскизный проект", "eskiz", "эскиз жоба"],
        weight=3,
    ),
    DocTypeDef(
        key="отчет_изысканий", label="Отчёт по изысканиям", section="main",
        keywords=["инженерно-геологическ", "инженерно-геодезическ", "изыскани", "геологиялық зерттеу"],
        weight=2,
    ),
    DocTypeDef(
        key="тех_условия", label="Технические условия", section="tech_conditions",
        keywords=["технические условия", "техусловия", "ту на", "на подключение", "техническое условие",
                  "техникалық шарттар"],
        weight=3,
    ),
    DocTypeDef(
        key="согласование", label="Согласование", section="approvals",
        keywords=["согласование", "согласовано", "санитарно-эпидемиологическое заключение",
                  "келісім", "келісілді"],
        weight=1,
    ),
    DocTypeDef(
        key="лицензия", label="Лицензия", section="approvals",
        keywords=["государственная лицензия", "лицензия", "лицензиат", "лицензияланған"],
        weight=2,
    ),
    DocTypeDef(
        key="протокол", label="Протокол", section="approvals",
        keywords=["протокол", "хаттама"],
        weight=1,
    ),
    DocTypeDef(
        key="справка", label="Справка", section="approvals",
        keywords=["справка", "анықтама"],
        weight=1,
    ),
    DocTypeDef(
        key="письмо", label="Письмо", section="main",
        keywords=["письмо", "хат", "касательно", "туралы"],
        weight=1,
    ),
]

SECTION_LABELS = {
    "main": "Основные документы",
    "tech_conditions": "Технические условия",
    "approvals": "Согласования и лицензии",
}

# ─────────────────────────────────────────────────────────────────────────────
# Классификация
# ─────────────────────────────────────────────────────────────────────────────

def classify(text: str) -> tuple[DocTypeDef, float]:
    """Возвращает (DocTypeDef, confidence 0..1)."""
    lower = text.lower()
    scores: dict[str, float] = {}
    weights: dict[str, int] = {}
    for dt in DOC_TYPES:
        score = sum(1 for kw in dt.keywords if kw.lower() in lower)
        anti = sum(1 for ak in dt.antikeywords if ak.lower() in lower)
        scores[dt.key] = (score - anti * 0.5) * dt.weight
        weights[dt.key] = dt.weight

    # при равном score побеждает больший weight (см. DocTypeDef.weight) —
    # без этого max() тихо брал первый по порядку в DOC_TYPES
    best_key = max(scores, key=lambda k: (scores[k], weights[k]))
    best_score = scores[best_key]
    if best_score <= 0:
        # неизвестный документ → письмо как fallback
        return next(d for d in DOC_TYPES if d.key == "письмо"), 0.1

    total = sum(max(s, 0) for s in scores.values()) or 1
    confidence = min(best_score / total, 1.0)
    return next(d for d in DOC_TYPES if d.key == best_key), round(confidence, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Извлечение реквизитов и форматирование
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(template: str, **kw) -> str:
    """Заполняет шаблон; незаполненные {} → [???]."""
    for k, v in kw.items():
        template = template.replace("{" + k + "}", v or "[???]")
    return template


def format_record(doc_type: DocTypeDef, text: str) -> dict:
    """Возвращает dict с extracted + formatted_text + notes."""
    k = doc_type.key
    date = _find_date(text)
    number = _find_number(text)
    org = _find_org(text)
    area = _find_area(text)
    year = _find_year(text)
    cadastral = _find_cadastral(text)
    subject = _first_line(text)

    notes = ""
    formatted = ""

    if k == "апз":
        formatted = _fmt(
            "архитектурно-планировочное задание на проектирование, выданное {org} от {date} — {number}",
            org=org, date=date, number=number,
        )
    elif k == "задание_на_проектирование":
        formatted = _fmt(
            "задание на проектирование, утверждённое {org} от {date}",
            org=org, date=date,
        )
    elif k == "акт_земля":
        formatted = _fmt(
            "акт на земельный участок {number}, кадастровый номер {cad}, площадью {area} га,"
            " изготовленный {org} от {date} года",
            number=number, cad=cadastral, area=area, org=org, date=date,
        )
    elif k == "акт_собственность":
        formatted = _fmt(
            "акт на право частной собственности на земельный участок — {number},"
            " Кадастровый номер {cad}, запись о выдаче — от {date}",
            number=number, cad=cadastral, date=date,
        )
    elif k == "решение_земля":
        # пытаемся найти вид землепользования
        land_type_m = re.search(
            r"(постоянног|временног|краткосрочног|долгосрочног)\w+\s+\w+пользовани\w+",
            text, re.IGNORECASE,
        )
        land_type = land_type_m.group(0).strip() if land_type_m else "[вид землепользования]"
        formatted = _fmt(
            "решение {org} о предоставлении права {land_type} для [цели],"
            " площадью {area} га, от {date} года — {number}",
            org=org, land_type=land_type, area=area, date=date, number=number,
        )
    elif k == "постановление":
        district_m = re.search(r"(?:Акимата?|акимата?)\s+([\wА-ЯЁа-яё\-]{3,40})", text)
        district = district_m.group(1).strip() if district_m else "[район/область]"
        formatted = _fmt(
            "постановление Акимата {district}, о передаче права [вид землепользования] {org},"
            " земельный участок площадью {area} га, от {date} года — {number}",
            district=district, org=org, area=area, date=date, number=number,
        )
    elif k == "договор_землепользования":
        formatted = _fmt(
            "договор временного возмездного землепользования земельного участка,"
            " между [государственный орган] и {org}, площадью {area} га,"
            " от {date} года — {number}",
            org=org, area=area, date=date, number=number,
        )
    elif k == "договор_купли_продажи":
        formatted = _fmt(
            "договор Купли-Продажи от {date} между [продавец] и [покупатель]",
            date=date,
        )
        notes = "ФИО сторон не извлечены автоматически — уточните вручную"
    elif k == "акт_обследования":
        formatted = _fmt(
            "акт обследования территории от {date} года, комиссии в составе {org}",
            date=date, org=org,
        )
    elif k == "дефектная_ведомость":
        formatted = _fmt(
            "дефектная ведомость, утверждённая {org} от {date} года",
            org=org, date=date,
        )
    elif k == "перечень_оборудования":
        formatted = _fmt(
            "перечень оборудования, материалов и изделий, утверждённый руководителем {org} от {date} г.",
            org=org, date=date,
        )
    elif k == "эскизный_проект":
        formatted = _fmt(
            "эскизный проект, разработанный {org} в {year} году",
            org=org, year=year,
        )
    elif k == "отчет_изысканий":
        lic_m = re.search(r"лицензи\w+[^,\n]*?[№#]\s*[\w\-]+", text, re.IGNORECASE)
        lic = lic_m.group(0).strip() if lic_m else "[лицензия]"
        formatted = _fmt(
            "отчёт по инженерно-геологическим изысканиям, выполненный {org} в {year} году ({lic})",
            org=org, year=year, lic=lic,
        )
    elif k == "тех_условия":
        tu_type_m = re.search(
            r"на\s+((?:подключение|присоединение|пересечение|водоснабж\w+|электроснабж\w+|"
            r"газоснабж\w+|теплоснабж\w+|канализац\w+|связ\w+|водоотведени\w+)[^\n,]{0,60})",
            text, re.IGNORECASE,
        )
        tu_type = tu_type_m.group(1).strip() if tu_type_m else "[тип подключения]"
        # убираем лишние кавычки если org уже содержит «»
        org_fmt = org if ("«" in org or '"' in org) else f"«{org}»"
        formatted = _fmt(
            "{org_fmt} — {number} от {date}, на {tu_type}",
            org_fmt=org_fmt, number=number, date=date, tu_type=tu_type,
        )
    elif k == "согласование":
        san_m = re.search(r"санитарно-эпидемиологическое заключение", text, re.IGNORECASE)
        if san_m:
            formatted = _fmt(
                "санитарно-эпидемиологическое заключение {org} — {number} от {date} г.",
                org=org, number=number, date=date,
            )
        else:
            formatted = _fmt(
                "письмо {org} — {number} от {date} года, касательно согласования проекта",
                org=org, number=number, date=date,
            )
    elif k == "лицензия":
        cat_m = re.search(r"категори\w+\s+([IVXivx\d]+)", text, re.IGNORECASE)
        cat = cat_m.group(1).strip() if cat_m else "[?]"
        lic_type_m = re.search(
            r"лицензи\w+\s+(?:на\s+)?([^\n,]{3,60}?)(?=\s+категори|\s+[–—-]|\s*$|\s+выдан)",
            text, re.IGNORECASE,
        )
        lic_type = lic_type_m.group(1).strip() if lic_type_m else "[вид деятельности]"
        formatted = _fmt(
            "государственная лицензия {lic_type} категории {cat} — {number} от {date} года,"
            " выданная [лицензиат], на имя {org}",
            lic_type=lic_type, cat=cat, number=number, date=date, org=org,
        )
    elif k == "протокол":
        proto_type_m = re.search(r"протокол\s+([^\n,]{3,60})", text, re.IGNORECASE)
        proto_type = proto_type_m.group(1).strip() if proto_type_m else "[тип]"
        formatted = _fmt(
            "протокол {proto_type} — {number} от {date} года, выполненный {org}",
            proto_type=proto_type, number=number, date=date, org=org,
        )
    elif k == "справка":
        formatted = _fmt(
            "справка {org} от {date} года — {number}, касательно {subject}",
            org=org, date=date, number=number, subject=subject[:80],
        )
    else:  # письмо / неизвестно
        formatted = _fmt(
            "письмо {org} от {date} года — {number}, касательно {subject}",
            org=org, date=date, number=number, subject=subject[:80],
        )

    return {
        "doc_type": k,
        "section": doc_type.section,
        "extracted": {
            "org_name": org,
            "date": date,
            "number": number,
            "subject": subject,
        },
        "formatted_text": formatted,
        "notes": notes,
    }


def process_document(text: str) -> dict:
    """Полный pipeline: text → classify → extract → format."""
    doc_type, confidence = classify(text)
    record = format_record(doc_type, text)
    record["confidence"] = confidence
    record["doc_type_label"] = doc_type.label
    return record
