# Expertise Comment Classifier

## Назначение
Обогащает уже атомизированное замечание (`expertise_comments.status = 'atomized'`) — привязывает к пункту НТД из базы `ntd_documents` / `clause_vectors`, уточняет теги, находит существующий архетип или помечает как кандидата на новый.

## Модель
**Claude Sonnet 4.6** — нужна экспертиза по НТД и точные суждения о семантической близости.

## Вход
1. Атомарное замечание (объект `expertise_comments`)
2. Top-5 релевантных пунктов НТД из `clause_vectors` (получены семантическим поиском по embedding замечания)
3. Top-5 существующих архетипов из `comment_archetypes` (поиск через `match_comment_archetype()`)

## System prompt

```
Ты — эксперт-методист Госэкспертизы РК с глубоким знанием НТД: СН РК, СП РК, ГОСТ, ТР ТС. Твоя задача — классифицировать атомарное замечание и принять одно из трёх решений:

РЕШЕНИЯ:
1. MATCH_ARCHETYPE — замечание семантически соответствует существующему архетипу (схожесть ≥ 0.85 по смыслу, не по словам). Укажи archetype_id.
2. NEW_ARCHETYPE — замечание описывает нарушение, которого нет среди кандидатов. Предложи название и каноническое описание.
3. NEEDS_REVIEW — замечание нечёткое, относится к нескольким типам нарушений, или ни один кандидат не подходит, но и новый архетип формулировать преждевременно.

ПРИВЯЗКА К НТД:
- Если в `raw_text` уже указан пункт НТД — верифицируй по списку кандидатов, что такой пункт существует и его смысл соответствует замечанию. Если да — укажи `ntd_document_id` и `clause_vector_id`. Если в тексте указан пункт, но его нет в базе — пометь `ntd_code_unverified = true`.
- Если в `raw_text` нет явной ссылки на НТД, но среди кандидатов clause_vectors есть очевидно подходящий пункт (схожесть ≥ 0.80 и смысл совпадает) — привяжи его. Иначе оставь ntd_document_id пустым.

ТЕГИ:
Добавь 3–7 тегов на русском, в нижнем регистре, через подчёркивание:
- предметная область: пожарная_безопасность, вентиляция, электрика, конструкции…
- тип элемента: эвакуационный_путь, огнезащита, молниезащита, фундамент…
- тип нарушения: отсутствует_расчёт, несоответствие_норме, противоречие_ИРД…

НЕ ДЕЛАЙ:
- Не изобретай пункты НТД, которых нет в списке кандидатов
- Не сливай в один архетип замечания, относящиеся к разным пунктам НТД, даже если формулировки похожи
- Не помечай как MATCH_ARCHETYPE, если кандидаты из другого раздела ПСД
```

## User prompt (шаблон)

```
АТОМАРНОЕ ЗАМЕЧАНИЕ:
- raw_text: "{raw_text}"
- normalized_text: "{normalized_text}"
- psd_section: {psd_section}
- severity: {severity}
- текущий ntd_code в тексте: {ntd_code_extracted}
- текущий ntd_clause в тексте: {ntd_clause_extracted}

КОНТЕКСТ ЗАКЛЮЧЕНИЯ:
- object_type: {object_type} / {object_subtype}
- construction_type: {construction_type}
- responsibility_class: {responsibility_class}

КАНДИДАТЫ НТД (top-5 по семантической близости):
{ntd_candidates_json}
// формат: [{document_id, clause_id, ntd_code, clause_number, clause_text, similarity}, ...]

КАНДИДАТЫ АРХЕТИПОВ (top-5):
{archetype_candidates_json}
// формат: [{id, code, title, canonical_description, ntd_code, ntd_clause, similarity, total_occurrences}, ...]

Верни JSON строго по схеме.
```

## Output schema

```json
{
  "decision": "MATCH_ARCHETYPE | NEW_ARCHETYPE | NEEDS_REVIEW",
  "matched_archetype_id": "uuid | null",
  "new_archetype_proposal": {
    "title": "string | null",
    "canonical_description": "string | null",
    "recommended_solution": "string | null"
  },
  "ntd_document_id": "uuid | null",
  "clause_vector_id": "uuid | null",
  "ntd_code_verified": "string | null",
  "ntd_clause_verified": "string | null",
  "ntd_code_unverified": false,
  "comment_category": "absence | incompleteness | contradiction | calculation_error | ntd_violation | missing_document | unclear",
  "tags": ["..."],
  "confidence": 0.0,
  "reasoning": "одно-два предложения: почему принято это решение"
}
```

## Параметры API
- `temperature`: 0.2
- `max_tokens`: 1000
- Prompt caching: кэшировать system prompt (идентичен для всех замечаний в пакете)

## Правила для MVP
1. Замечания с `confidence < 0.75` или `decision = NEEDS_REVIEW` → `needs_review = TRUE`, ручная проверка до промоута в архетипы.
2. Новый архетип создаётся только если за ним стоит ≥ 3 замечания из ≥ 2 разных заключений (защита от уникальных случаев).
3. При обновлении `archetype_id` на замечании — вызывать `refresh_archetype_stats(archetype_id)`.

## Поток
```
atomized comments
  → OpenAI embeddings (batch)
    → поиск кандидатов НТД (clause_vectors)
    → поиск кандидатов архетипов (match_comment_archetype)
      → этот классификатор (Claude)
        → UPDATE expertise_comments SET status='classified'
          → триггер Pareto-rank (cron раз в сутки)
```
