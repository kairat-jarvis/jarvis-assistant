# JARVIS — Персональный AI-оркестратор

> «Ты не нанимаешь людей. Ты оцифровываешь себя и создаёшь армию агентов.»

Система персонального AI-оркестратора, превращающая поток сознания в конкретные действия через специализированных AI-агентов. Claude сам является оркестратором, используя MCP-серверы как инструменты.

## Архитектура (dual-backend)

- **Интерфейс**: Claude App на телефоне (claude.ai Project)
- **Оркестратор**: Claude, системный промпт — `JARVIS_SYSTEM_PROMPT.md`
- **Память, локально** (приоритет для Python и Claude Code): PostgreSQL 17 + pgvector —
  `jarvis_local` (`jarvis_memory`, `jarvis_projects`, `jarvis_agent_logs`) и `expertise_ntd`
  (`ntd_documents`, `clause_vectors`). Drop-in клиенты — `scripts/jarvis_local.py`,
  `scripts/ntd_local.py`. План редиректа — `db/REDIRECT.md`.
- **Память, cloud** (для n8n и claude.ai Project): Supabase — те же таблицы, периодически
  синхронизируются в локальную БД (`scripts/migrate_jarvis_from_supabase.py`).
- **Инструменты**: MCP-серверы (Supabase, Google Drive, Calendar, Gmail, Notion, Firecrawl)
- **Автономные задачи**: n8n (только cron — AI-мониторинг, дайджесты → Telegram push)

Подробности — `CLAUDE.md` (правила проекта) и `JARVIS_CONCEPT.md` (концепт).

## Структура

```
jarvis-assistant/
├── CLAUDE.md                   # Главная инструкция проекта
├── JARVIS_SYSTEM_PROMPT.md     # Системный промпт для Claude Project
├── JARVIS_CONCEPT.md           # Детальный концепт (справочный)
├── JARVIS_TEST_PLAN.md         # План тестирования
├── db/                         # Схемы локального PG + план миграции с Supabase
├── scripts/                    # Клиенты памяти, НТД-загрузчик, Notion/АГСК-3 утилиты
├── n8n_workflows/              # Экспортированные workflow (кредлы — плейсхолдеры)
├── vypiska_ird/                # Десктоп-приложение: выписки ИРД из PDF
├── docs/                       # Вспомогательная документация
├── ideas/                      # Захваченные идеи (idea harvest)
├── prompts/                    # Промпты для Claude
└── .claude/skills/             # Библиотека Claude Code Skills проекта
```

## Связанные проекты

- `claude-assistant` — 25+ инженерных скилов и промптов
- `expertise-orchestrator` — multi-agent CLI для экспертизы ПД
- `ntd-qdrant-mcp` — MCP-сервер НТД-поиска
- `agsk3-workspace` — каталог АГСК-3

## Статус

🟢 Фаза 1 — Dual-backend память в работе

- ✅ Локальный PostgreSQL (`jarvis_local`, `expertise_ntd`) — основной источник истины
- ✅ Supabase — облачное зеркало для n8n/claude.ai, периодическая синхронизация
- ✅ JARVIS Project на claude.ai с системным промптом
- ✅ Десктоп-приложение `vypiska_ird` для выписок ИРД
- ✅ Библиотека Claude Code Skills (`.claude/skills/`)
- 🟡 Загрузчик новой НТД в локальный PG (`scripts/ntd_loader/`) — в разработке
