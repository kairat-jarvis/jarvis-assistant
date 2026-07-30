"""Тесты классификации ИРД-документов (ird_extract.classifier).

Покрывает главную нетривиальную логику приложения без тестов: keyword-scoring,
antikeyword-подавление, fallback на неизвестный тип и tie-break по weight.
"""
from __future__ import annotations

from ird_extract import classifier
from ird_extract.classifier import DocTypeDef, classify, process_document


def test_apz_classified_by_keyword():
    text = "Архитектурно-планировочное задание выдано ГУ Архитектуры от 12 мая 2026 года № 123"
    dt, confidence = classify(text)
    assert dt.key == "апз"
    assert confidence > 0


def test_antikeyword_prevents_apz_match():
    """'задание на проектирование' не должно классифицироваться как АПЗ (antikeyword)."""
    text = "Задание на проектирование утверждено директором от 01 июня 2026 года"
    dt, _ = classify(text)
    assert dt.key == "задание_на_проектирование"


def test_unknown_text_falls_back_to_pismo():
    dt, confidence = classify("Совершенно нечитаемый текст без единого ключевого слова")
    assert dt.key == "письмо"
    assert confidence == 0.1


def test_tech_usloviya_end_to_end_format():
    text = "Технические условия № ТУ-45 от 10.03.2026 на водоснабжение объекта"
    record = process_document(text)
    assert record["doc_type"] == "тех_условия"
    assert record["section"] == "tech_conditions"
    assert "formatted_text" in record and record["formatted_text"]
    assert set(record["extracted"]) == {"org_name", "date", "number", "subject"}


def test_process_document_never_raises_on_empty_text():
    record = process_document("")
    assert record["doc_type"] == "письмо"
    assert record["formatted_text"]


def test_tie_break_prefers_higher_weight(monkeypatch):
    """При равном итоговом score побеждает тип с большим weight, а не первый в списке."""
    # low: 3 keyword hits * weight 1 = 3
    low_weight_first = DocTypeDef(
        key="low", label="Low", section="main",
        keywords=["альфа", "бета", "гамма"], weight=1,
    )
    # high: 1 keyword hit * weight 3 = 3 → тот же итоговый score, но выше приоритет
    high_weight_second = DocTypeDef(
        key="high", label="High", section="main",
        keywords=["дельта"], weight=3,
    )
    monkeypatch.setattr(classifier, "DOC_TYPES", [low_weight_first, high_weight_second])

    dt, _ = classify("альфа бета гамма дельта")
    assert dt.key == "high"
