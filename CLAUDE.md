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

## Ключевые файлы
- `JARVIS_SYSTEM_PROMPT.md` — системный промпт для Claude Project на claude.ai
- `JARVIS_CONCEPT.md` — детальный концепт (справочный)
- `scripts/setup_supabase.sql` — SQL-схема (уже применена)
- `n8n_workflows/` — workflow для автономных задач

## Связанные проекты (G:\Мой диск\AI\Claude Code\)
- `RAG-Consultant/` — Supabase SQL-паттерны, RAG pipeline
- `Claude Assistant/` — 25+ навыков, промпты инженерных агентов
- `n8n-mcp/` — MCP-сервер для n8n автоматизации
- `FIRECRAWL/` — веб-скрейпинг для AI-мониторинга

## Правила
1. Все идеи и заметки ОБЯЗАТЕЛЬНО сохранять в jarvis_memory
2. Каждую идею оценивать количественно (feasibility + impact)
3. Действия логировать в jarvis_agent_logs
4. По нормам — СНАЧАЛА искать в базе НТД
5. n8n только для автономных cron-задач, НЕ для интерфейса
6. **OCR — ВСЕГДА и ВЕЗДЕ только PaddleOCR-VL-1.5.** Никаких других OCR-движков (Tesseract, EasyOCR, Claude Vision в роли OCR, PaddleOCR версий < 1.5, doctr, Surya и т.п.) не использовать. Любое распознавание текста из сканов / PDF / изображений идёт строго через PaddleOCR-VL-1.5. Это правило распространяется на все агенты (ird_extractor, visual-analysis-ocr, psd_expert и др.) и все pipeline (ИРД, НТД, ПСД, КИПиА, спецификации АГСК-3).
