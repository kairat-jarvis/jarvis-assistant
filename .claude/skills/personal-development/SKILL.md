---
name: personal-development
description: JARVIS управляет личным развитием пользователя как Winston-оркестратор. Три активных трека: AI/ML инженерия, Предпринимательство, Языки и коммуникация. Используй когда: «добавь цель», «зафиксируй прогресс», «что я изучал», «план на трек», «недельный обзор», «оцени прогресс по AI», «добавь ресурс», «что читать по ML».
---

# Personal Development — JARVIS как личный куратор развития

JARVIS (Winston-оркестратор) ведёт три трека компетенций.
Все данные хранятся в `jarvis_memory` с `related_project="Личное развитие 2026"`.

---

## Три трека

| Трек | Код | Суть |
|------|-----|------|
| AI/ML инженерия | `ai-ml` | LLM-интеграции, агенты, RAG, fine-tuning, MLOps, архитектура систем |
| Предпринимательство | `biz` | Продуктовое мышление, стратегия, бизнес-модели, управление проектами |
| Языки и коммуникация | `lang` | Английский, казахский, публичные выступления, написание документов |

---

## Типы записей в jarvis_memory

| `content_type` | Когда использовать |
|----------------|-------------------|
| `task` | Конкретная учебная задача с дедлайном |
| `note` | Прочитанный материал, факт, инсайт |
| `idea` | Концепт для применения, «а что если» |
| `decision` | Смена направления, выбор фреймворка/языка |
| `digest` | Недельный / месячный обзор прогресса |

Тег трека (`ai-ml`, `biz`, `lang`) — обязательный в `tags`.

---

## Алгоритмы по режимам

### Режим A — Фиксация прогресса («прочитал», «сделал», «понял»)

1. Определи трек по контексту
2. Проверь дубль: `cli.fts_only(query_text=summary, count=2)`
3. Сохрани:

```python
from scripts.jarvis_local import JarvisLocal
cli = JarvisLocal()
new_id = cli.add_memory(
    content="[Полное описание: что сделал/изучил/понял]",
    content_type="note",
    summary="[1 предложение]",
    tags=["личное-развитие", "ai-ml"],   # или biz / lang
    priority="medium",
    related_project="Личное развитие 2026",
    metadata={
        "track": "ai-ml",
        "session_date": "2026-05-27",
        "resource": "название книги/курса/статьи",  # если есть
        "skill_level_delta": "+1",                   # опционально
    },
)
cli.log_action(
    agent_id="personal-development",
    action="log_progress",
    input_data={"track": "ai-ml", "content_type": "note"},
    output_data={"memory_id": str(new_id)},
    status="success",
)
```

### Режим B — Новая учебная задача / план

1. Уточни трек, тему, дедлайн (если не указан — `priority="low"`)
2. Проверь, нет ли похожей задачи: `fts_only(query_text=summary, count=2)`
3. Сохрани как `content_type="task"`:

```python
cli.add_memory(
    content="Изучить архитектуру MoE (Mixture of Experts): прочитать статью Mixtral, написать конспект, реализовать toy-пример.",
    content_type="task",
    summary="Изучить MoE — статья Mixtral + toy impl",
    tags=["личное-развитие", "ai-ml", "архитектуры"],
    priority="high",
    related_project="Личное развитие 2026",
    metadata={
        "track": "ai-ml",
        "due_date": "2026-06-10",
        "session_date": "2026-05-27",
        "status": "todo",
    },
)
```

### Режим C — Недельный / месячный обзор

Запрос: «итоги недели по развитию» или «что я делал по AI за месяц».

```python
# Получить все записи трека за период
import psycopg, json
from datetime import datetime, timedelta

with psycopg.connect("postgresql://localhost/jarvis_local") as conn:
    rows = conn.execute("""
        SELECT id, content_type, summary, metadata, created_at
        FROM jarvis_memory
        WHERE related_project = 'Личное развитие 2026'
          AND metadata->>'track' = 'ai-ml'
          AND created_at >= NOW() - INTERVAL '7 days'
        ORDER BY created_at DESC
    """).fetchall()

for r in rows:
    print(r[1], "|", r[2], "|", r[4].strftime("%d.%m"))
```

После сбора — синтезировать в `content_type="digest"`:
```python
cli.add_memory(
    content="[Развёрнутый текст дайджеста — что сделано, что на паузе, инсайты]",
    content_type="digest",
    summary="Дайджест AI/ML: неделя 22 (19–25 мая 2026)",
    tags=["личное-развитие", "ai-ml", "дайджест"],
    priority="medium",
    related_project="Личное развитие 2026",
    metadata={"track": "ai-ml", "period": "2026-W22", "session_date": "2026-05-27"},
)
```

### Режим D — Поиск по треку («что я изучал», «открытые задачи по бизнесу»)

```python
# FTS-поиск:
results = cli.fts_only(query_text="бизнес-модель предпринимательство", count=10)

# Или прямой SQL — открытые задачи:
with psycopg.connect("postgresql://localhost/jarvis_local") as conn:
    rows = conn.execute("""
        SELECT summary, metadata->>'due_date', priority
        FROM jarvis_memory
        WHERE content_type = 'task'
          AND related_project = 'Личное развитие 2026'
          AND metadata->>'status' != 'done'
        ORDER BY priority DESC, created_at
    """).fetchall()
```

### Режим E — Закрытие задачи («сделал задачу по английскому»)

```python
# Обновить статус через прямой SQL:
with psycopg.connect("postgresql://localhost/jarvis_local") as conn:
    conn.execute("""
        UPDATE jarvis_memory
        SET metadata = metadata || '{"status": "done", "completed_date": "2026-05-27"}'
        WHERE id = '<uuid>'
    """)
    conn.commit()
```

---

## Уровни компетенций (для тега `skill_level`)

| Уровень | Описание |
|---------|----------|
| `novice` | Базовые понятия, первые шаги |
| `practitioner` | Самостоятельная работа на реальных задачах |
| `advanced` | Проектирование, оптимизация, менторинг |
| `expert` | Публичные материалы, R&D, авторитетное мнение |

Текущий стартовый уровень (2026-05-27):
- `ai-ml` → `practitioner` (работающие системы: JARVIS, expertise-orchestrator, NTD-loader)
- `biz` → `novice-practitioner` (ведёт реальные проекты, строит MVP)
- `lang` → `practitioner` (en), `novice` (kz)

---

## Что НЕ делать

- ❌ Не создавать отдельный проект — всё идёт в «Личное развитие 2026»
- ❌ Не дублировать задачи — сначала FTS-чек
- ❌ Не сохранять без тега трека (`ai-ml`, `biz`, `lang`)
- ❌ Не игнорировать дайджесты — они позволяют JARVIS видеть динамику

---

## Быстрые команды

```bash
# Открытые задачи по всем трекам
cd "/Users/kairat/Claude Code/JARVIS ASSISTANT"
.venv/bin/python -c "
import psycopg
with psycopg.connect('postgresql://localhost/jarvis_local') as conn:
    rows = conn.execute(\"\"\"
        SELECT metadata->>'track', summary, priority, metadata->>'due_date'
        FROM jarvis_memory
        WHERE content_type='task' AND related_project='Личное развитие 2026'
          AND (metadata->>'status' IS NULL OR metadata->>'status' != 'done')
        ORDER BY metadata->>'track', priority DESC
    \"\"\").fetchall()
    for r in rows: print(r)
"

# Последние 10 записей по ai-ml
.venv/bin/python -c "
import psycopg
with psycopg.connect('postgresql://localhost/jarvis_local') as conn:
    rows = conn.execute(\"\"\"
        SELECT content_type, summary, created_at::date
        FROM jarvis_memory
        WHERE related_project='Личное развитие 2026'
          AND metadata->>'track'='ai-ml'
        ORDER BY created_at DESC LIMIT 10
    \"\"\").fetchall()
    for r in rows: print(r)
"
```
