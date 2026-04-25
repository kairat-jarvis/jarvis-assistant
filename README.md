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
JARVIS ASSISTANT/
├── CLAUDE.md                   # Главная инструкция проекта
├── JARVIS_SYSTEM_PROMPT.md     # Системный промпт для Claude Project
├── JARVIS_CONCEPT.md           # Детальный концепт (справочный)
├── JARVIS_TEST_PLAN.md         # План тестирования
├── scripts/
│   └── setup_supabase.sql      # SQL-схема (применена)
└── n8n_workflows/              # Экспортированные workflows
```

## Связанные проекты

- `claude-assistant` — 25+ инженерных скилов и промптов
- `rag-consultant` — RAG pipelines для НТД
- `firecrawl-tools` — веб-скрейпинг
- `n8n-mcp` — MCP сервер для n8n
- `agsk3-workspace` — каталог АГСК-3
- `ird-extract` — ИРД экстрактор

## Ресурсы

- [Claude Code quickstart (desktop tutorial)](https://docs.claude.com/en/docs/claude-code/quickstart)

## Статус
🟢 Фаза 0 — Фундамент (в процессе)

- ✅ Supabase таблицы + RPC функции
- ✅ JARVIS Project на claude.ai с системным промптом
- ✅ Первая идея сохранена в память
- 🟡 Миграция на GitHub (текущий шаг)
- ⏳ n8n workflows для автономных задач
