# JARVIS — Персональный AI-оркестратор

## Проект
JARVIS — система персонального AI-оркестратора, превращающая поток сознания (голос, текст, идеи) в конкретные действия. Claude сам является оркестратором, используя MCP серверы как инструменты.

## Архитектура: Claude-native
- **Интерфейс**: Claude App на телефоне (claude.ai Project)
- **Оркестратор**: Claude (системный промпт = JARVIS_SYSTEM_PROMPT.md)
- **Память**: Supabase MCP → jarvis_memory, jarvis_projects, jarvis_agent_logs
- **Инструменты**: MCP серверы (Supabase, Google Drive, Calendar, Gmail, Notion, Firecrawl)
- **Автономные задачи**: n8n (только cron: AI-мониторинг, дайджесты → Telegram push)
- Telegram Bot — только для push-уведомлений от n8n, НЕ для общения

## Supabase (проект: omykcphkzmmqpwswwfsw)

### JARVIS таблицы
- `jarvis_memory` — второй мозг (идеи, заметки, задачи, отчёты)
- `jarvis_projects` — контексты проектов
- `jarvis_agent_logs` — аудит действий
- `match_jarvis_memory()` — RPC для семантического поиска
- `get_jarvis_stats()` — RPC для статистики

### Существующие таблицы (НЕ трогать)
- `documents` (166) — RAG-Consultant
- `ntd_documents` (395) — база НТД
- `agsk_catalog` (233,966) — каталог АГСК-3
- `clause_vectors` (90,262) — пункты нормативов

## Структура репозитория
```
jarvis-assistant/
├── CLAUDE.md                   ← эта инструкция
├── JARVIS_SYSTEM_PROMPT.md     ← системный промпт для Claude Project
├── JARVIS_CONCEPT.md           ← детальный концепт
├── JARVIS_TEST_PLAN.md         ← план тестирования
├── scripts/setup_supabase.sql  ← SQL-схема (применена)
├── n8n_workflows/              ← экспорт workflow'ов
└── tools/                      ← реестр внешних инструментов
    ├── REGISTRY.md             ← главная карта: какой инструмент когда
    └── <name>/TOOL.md          ← карточка: назначение, MCP, правила
```

## Модульная архитектура инструментов
Каждый инструмент — отдельный репо `github.com/kairat-jarvis/<name>`.
В этом репо только **карточки** (`tools/<name>/TOOL.md`), не сам код.
Это экономит контекст: JARVIS подгружает карточку только когда сработал триггер.

### Навигация по инструментам
1. Перед делегированием специализированной задачи — открыть `tools/REGISTRY.md`.
2. Найти триггер в таблице → открыть `tools/<name>/TOOL.md`.
3. Следовать правилам и MCP-зависимостям из карточки.
4. Если триггера нет — работать стандартными MCP (Supabase, Drive, Calendar, Gmail, Notion).
5. Новый инструмент добавляется по шаблону из `tools/REGISTRY.md` (раздел «Как добавить»).

### Текущие инструменты
См. полный список в `tools/REGISTRY.md`. Кратко:
- `rag-consultant` — НТД / нормативы
- `claude-assistant` — инженерные агенты (25+)
- `n8n-mcp` — автономные cron-задачи
- `firecrawl-tools` — веб-скрейпинг
- `agsk3-workspace` — каталог АГСК-3
- `ird-extract` — ИРД / ТУ / ГПЗУ

## Правила
1. Все идеи и заметки ОБЯЗАТЕЛЬНО сохранять в `jarvis_memory`.
2. Каждую идею оценивать количественно (feasibility + impact).
3. Действия логировать в `jarvis_agent_logs` (с полем `tool=<имя>` если использовался модуль).
4. По нормам — СНАЧАЛА искать в базе НТД (`rag-consultant`).
5. n8n только для автономных cron-задач, НЕ для интерфейса.
6. Перед специализированной задачей — свериться с `tools/REGISTRY.md`.
