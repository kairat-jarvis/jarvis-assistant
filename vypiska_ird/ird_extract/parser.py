"""Парсинг структурированных полей ИРД из сырого текста."""

from __future__ import annotations

import re
from typing import Dict

from .fields import FIELDS


def normalize_whitespace(text: str) -> str:
    """Схлопывает переносы строк внутри значений полей ИРД.

    Порядок шагов важен:
    1. Убираем дефис переноса слова (мягкий перенос в PDF).
    2. Склеиваем строки с отступом — pdfplumber часто делает так для многострочных значений.
    3. Склеиваем строки, начинающиеся с маленькой буквы (a-z, а-яё) или цифры.
    4. Нормализуем повторные пробелы/табы.
    """
    # шаг 1: мягкий перенос слова через дефис
    text = re.sub(r"-\n", "", text)
    # шаг 2: отступленные продолжения (начинаются с пробела/таба)
    text = re.sub(r"\n[ \t]+", " ", text)
    # шаг 3: продолжения, начинающиеся с маленькой буквы или цифры (вкл. Ё/ё)
    text = re.sub(r"\n(?=[a-zа-яё0-9])", " ", text)
    # шаг 4: нормализация пробелов
    text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_fields(text: str) -> Dict[str, str]:
    """Прогоняет все паттерны, возвращает словарь {field_key: value}."""
    norm = normalize_whitespace(text)
    result: Dict[str, str] = {}
    for field in FIELDS:
        value = ""
        for pattern in field["patterns"]:
            match = re.search(pattern, norm, flags=re.IGNORECASE)
            if match:
                value = (match.group(1) if match.groups() else match.group(0)).strip()
                value = re.sub(r"\s+", " ", value).rstrip(",.;: ")
                break
        result[field["key"]] = value
    return result
