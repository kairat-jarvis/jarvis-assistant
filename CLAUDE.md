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
6. **Извлечение текста из документов — строго трёхуровневый waterfall, порядок обязателен:**
   1. **pdfplumber** — для текстовых PDF (selectable text). Если текст извлечён уверенно (≥ порога покрытия страницы / уверенности) — стоп, дальше не идём.
   2. **PaddleOCR-VL-1.5** — единственный OCR-движок для сканов, фото, PDF-изображений, чертежей, штампов, рукописей. Используется, если pdfplumber не дал текста или дал мусор. Запрещены Tesseract, EasyOCR, doctr, Surya, PaddleOCR версий < 1.5.
   3. **Claude Vision** — последний fallback, только если PaddleOCR-VL-1.5 не справился (низкая уверенность, нечитаемый/рукописный/поврежденный документ, сложный layout). Claude Vision НЕ может использоваться как OCR первого выбора и не может пропускать уровни 1–2.
   Правило распространяется на все агенты (ird_extractor, visual-analysis-ocr, psd_expert, fire-ss-agent, normative-agent и др.) и все pipeline (ИРД, НТД, ПСД, КИПиА, спецификации АГСК-3). Каждое обращение к уровню 3 логируется в jarvis_agent_logs с причиной fallback.
