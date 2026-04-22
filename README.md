# JARVIS — Персональный AI-оркестратор

> «Ты не нанимаешь людей. Ты оцифровываешь себя и создаёшь армию агентов.»

Система персонального AI-оркестратора, превращающая поток сознания в конкретные действия через специализированных AI-агентов.

## Архитектура

- **Интерфейс**: Claude App на телефоне (claude.ai Project)
- **Оркестратор**: Claude с системным промптом JARVIS
- **Память**: Supabase pgvector (jarvis_memory, jarvis_projects, jarvis_agent_logs)
- **Инструменты**: MCP серверы (Supabase, Google Drive, Calendar, Gmail, Notion, Firecrawl, Perplexity, GitHub, n8n)
- **Автономные задачи**: n8n cloud (AI-мониторинг, дайджесты)
- **Код и промпты**: GitHub (kairat-jarvis organization)

## Структура

```
jarvis-assistant/
├── CLAUDE.md                   # Главная инструкция проекта
├── JARVIS_SYSTEM_PROMPT.md     # Системный промпт для Claude Project
├── JARVIS_CONCEPT.md           # Детальный концепт (справочный)
├── JARVIS_TEST_PLAN.md         # План тестирования
├── scripts/
│   └── setup_supabase.sql      # SQL-схема (применена)
├── n8n_workflows/              # Экспортированные workflows
└── tools/                      # Реестр внешних инструментов
    ├── REGISTRY.md             # Карта: какой инструмент когда использовать
    ├── rag-consultant/TOOL.md
    ├── claude-assistant/TOOL.md
    ├── n8n-mcp/TOOL.md
    ├── firecrawl-tools/TOOL.md
    ├── agsk3-workspace/TOOL.md
    └── ird-extract/TOOL.md
```

## Модульная архитектура

Каждый инструмент — **отдельный репозиторий** в `github.com/kairat-jarvis`. В этом репо хранятся только
**карточки инструментов** (`tools/<name>/TOOL.md`) — не сам код. JARVIS-оркестратор держит в контексте
лёгкий реестр (`tools/REGISTRY.md`) и подгружает карточку конкретного инструмента только когда
сработал триггер. Это экономит контекст и позволяет обновлять инструменты независимо.

Подробнее — в [tools/REGISTRY.md](tools/REGISTRY.md).

## Связанные репозитории

| Репо | Домен |
|---|---|
| [`claude-assistant`](tools/claude-assistant/TOOL.md) | 25+ инженерных скилов и промптов |
| [`rag-consultant`](tools/rag-consultant/TOOL.md) | RAG pipelines для НТД |
| [`n8n-mcp`](tools/n8n-mcp/TOOL.md) | MCP сервер для n8n |
| [`firecrawl-tools`](tools/firecrawl-tools/TOOL.md) | веб-скрейпинг |
| [`agsk3-workspace`](tools/agsk3-workspace/TOOL.md) | каталог АГСК-3 |
| [`ird-extract`](tools/ird-extract/TOOL.md) | ИРД экстрактор |

## Статус
🟢 Фаза 0 — Фундамент (в процессе)

- ✅ Supabase таблицы + RPC функции
- ✅ JARVIS Project на claude.ai с системным промптом
- ✅ Первая идея сохранена в память
- 🟡 Миграция на GitHub (текущий шаг)
- ⏳ n8n workflows для автономных задач
