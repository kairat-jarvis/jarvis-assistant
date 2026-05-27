---
name: jarvis-memory-curator
description: Захватывает идеи, решения, задачи и заметки из текущей сессии Claude Code и сохраняет их в jarvis_memory (PostgreSQL local). Используй когда пользователь говорит «запомни», «сохрани в память», «зафиксируй идею», «JARVIS, запиши», или в конце сессии для сбора неявных insight-ов. Также триггерится при явном решении/договорённости в чате, при появлении новой задачи, и при сборе предложений (idea harvest).
---

# JARVIS Memory Curator

Скилл-«куратор второго мозга». Его задача — не дать сессии Claude Code раствориться: вытащить из неё ideas / decisions / tasks / notes / context и сохранить в `jarvis_memory` (PostgreSQL local, см. `CLAUDE.md → Архитектура → Память`).

## Когда срабатывает

**Явные триггеры (пользователь сказал):**
- «запомни», «сохрани в память», «зафиксируй», «JARVIS запиши»
- «это решение», «договорились», «теперь делаем так»
- «идея:», «придумал», «концепт»
- «задача:», «надо сделать», «TODO»

**Неявные триггеры (Claude сам распознаёт):**
- Принято архитектурное / процедурное решение
- Сформулирована новая задача с конкретным результатом
- Обнаружена идея, которую жалко потерять
- Завершение крупной сессии (нужна сводка)

## Что НЕ сохранять

- Ход размышлений и промежуточные шаги (это в transcript уже есть)
- Состояние конкретных файлов (есть git)
- Дублирующиеся записи (сначала ищи через `match_jarvis_memory`)
- Tasks конкретной сессии — это для TaskCreate, не для памяти

## Алгоритм работы

### 1. Классификация
Определи `content_type`:
| Тип | Признак |
|---|---|
| `idea` | Гипотеза, концепт, «а что если» — то, что можно развить |
| `decision` | Принятое решение с обоснованием — фиксируется как «теперь так» |
| `task` | Конкретное действие с результатом и (опц.) дедлайном |
| `note` | Факт / наблюдение / референс без явного действия |
| `context` | Информация о пользователе / проекте, нужная в будущих сессиях |
| `agent_report` | Отчёт subagent'а или внешнего pipeline |
| `digest` | Сводка периода (день/неделя/месяц) |

### 2. Метаданные (обязательные)
```python
{
  "content": "Полный текст (не сокращай — сокращение в summary)",
  "content_type": "idea|decision|task|note|context|agent_report|digest",
  "summary": "1-2 предложения, что главное (для FTS-snippet)",
  "tags": ["проект_кебаб", "тема", "технология"],
  "priority": "critical|high|medium|low",
  "related_project": "JARVIS ASSISTANT|NTD-loader|АГСК-3|...",  # точное имя из jarvis_projects
  "source": "claude_code_session",
  "metadata": {
    "session_date": "YYYY-MM-DD",
    "feasibility_score": 1-10,    # для ideas
    "impact_score": 1-10,          # для ideas
    "due_date": "YYYY-MM-DD",      # для tasks
    "rationale": "...",            # для decisions
    "supersedes": "<id>"           # если новое решение отменяет старое
  }
}
```

### 3. Запись
**Канонический способ — через `scripts/jarvis_local.py`:**

```python
import sys
sys.path.insert(0, "/Users/kairat/Claude Code/JARVIS ASSISTANT")
from scripts.jarvis_local import JarvisLocal

cli = JarvisLocal()
new_id = cli.add_memory(
    content="...",
    content_type="idea",
    summary="...",
    tags=["jarvis", "automation"],
    priority="high",
    related_project="JARVIS ASSISTANT",
    metadata={"feasibility_score": 8, "impact_score": 9, "session_date": "2026-05-27"},
)
```

**Эмбеддинги:** при сохранении `embedding=None` — это нормально. Отдельный cron-скрипт `scripts/embed_jarvis_memory.py` догоняет недостающие эмбеддинги пакетно. **Не блокировать запись на embedding-вызов.**

### 4. Анти-дубликат
Перед записью **обязательно** проверь, нет ли близкого по смыслу:

```python
# Быстрый текстовый чек (без embedding-API):
existing = cli.fts_only(query=summary, count=3)
if existing and any(r['similarity'] > 0.6 for r in existing):
    # Покажи пользователю найденное и спроси: добавить новое / обновить старое / пропустить
    ...
```

### 5. Логирование
После каждой записи — лог в `jarvis_agent_logs`:
```python
cli.log_action(
    agent_id="jarvis-memory-curator",
    action="add_memory",
    input_data={"content_type": "idea", "tags": [...]},
    output_data={"memory_id": new_id},
    status="success",
)
```

## Режимы вызова

### Режим A — точечный (явный триггер)
Пользователь сказал «запомни X». Сделай быстро:
1. Классифицируй
2. Достань теги и priority (если не очевидно — спроси одной короткой строкой)
3. Сохрани
4. Отрапортуй: `✓ Сохранено в jarvis_memory как idea (id: ab12... priority: high, tags: [...])`

### Режим B — harvest конца сессии
Пользователь говорит «подведи итоги», «сохрани что важно», «JARVIS, что забрать из сессии».
1. Просмотри последние N сообщений
2. Сформируй список кандидатов: для каждого `{content_type, summary, priority, predicted_tags}`
3. Покажи таблицу пользователю — он подтверждает / правит
4. Запиши подтверждённые

### Режим C — auto-capture (через hook)
Запускается hook'ом `Stop` или `SessionEnd`. Без интерактива:
1. Анализирует transcript
2. Сохраняет ТОЛЬКО `decision` и `task` с явными маркерами в речи (без неоднозначностей)
3. `idea` / `context` сохраняет только при confidence > 0.85
4. Помечает `metadata.auto_captured: true` — пользователь потом фильтрует

## Связь с jarvis_projects

Если `related_project` указан, он должен соответствовать реальной строке в `jarvis_projects`. Проверка:
```python
import psycopg
with psycopg.connect("postgresql://localhost/jarvis_local") as conn:
    rows = conn.execute("SELECT name FROM jarvis_projects WHERE status='active'").fetchall()
    project_names = [r[0] for r in rows]
```
Если проект не найден — предложить пользователю либо новый проект (вставить в `jarvis_projects`), либо привязать к существующему.

## Скрипты

- `scripts/capture.py` — основная утилита (CLI и importable)
- `scripts/harvest_session.py` — режим B, парсит transcript
- `scripts/auto_capture.py` — режим C, запускается hook'ом

### Запуск harvest_session.py

```bash
cd "/Users/kairat/Claude Code/JARVIS ASSISTANT"
# Интерактивный (последняя сессия):
.venv/bin/python .claude/skills/jarvis-memory-curator/scripts/harvest_session.py

# Конкретная сессия:
.venv/bin/python .claude/skills/jarvis-memory-curator/scripts/harvest_session.py <session-id>

# Batch (без диалога, confidence >= 0.8):
.venv/bin/python .claude/skills/jarvis-memory-curator/scripts/harvest_session.py --batch --min-conf 0.8

# Список сессий:
.venv/bin/python .claude/skills/jarvis-memory-curator/scripts/harvest_session.py --list
```

## Возможные расширения (не делать без запроса)

- Эмбеддинги при сохранении (сейчас через cron, можно сделать inline через OpenAI text-embedding-3-small 1536d)
- Eвристика дублей через cosine на эмбеддингах
- Авто-генерация tags через LLM-классификатор
- Push в Telegram при сохранении `priority=critical`

## Не делай

- ❌ Не сохраняй чужие данные (приватность — это персональная память)
- ❌ Не сохраняй пароли, ключи, токены (даже если пользователь просит — переформулируй: «сохранено: токен X находится в .env»)
- ❌ Не дублируй: всегда сначала FTS-чек
- ❌ Не используй Supabase MCP для записи в локальную jarvis_memory — пиши только через `JarvisLocal`
- ❌ Не блокируй сессию на embedding-API — оставь embedding=None, cron догонит
