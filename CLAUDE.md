# JARVIS — Персональный AI-оркестратор

## Проект
JARVIS — система персонального AI-оркестратора, превращающая поток сознания (голос, текст, идеи) в конкретные действия. Claude сам является оркестратором, используя MCP серверы как инструменты.

## Архитектура: Claude-native (dual-backend)
- **Интерфейс**: Claude App на телефоне (claude.ai Project)
- **Оркестратор**: Claude (системный промпт = JARVIS_SYSTEM_PROMPT.md)
- **Память (локально, приоритет для Python и Claude Code)**:
  - `postgresql://localhost/jarvis_local` — `jarvis_memory`, `jarvis_projects`, `jarvis_agent_logs`
  - `postgresql://localhost/expertise_ntd` — `ntd_documents` (395) + `clause_vectors` (90 368)
  - Drop-in клиенты с теми же сигнатурами что Supabase RPC:
    `scripts/jarvis_local.py` (`JarvisLocal`) и `scripts/ntd_local.py` (`NtdLocal`).
  - План редиректа и регламент синхронизации — `db/REDIRECT.md`.
- **Память (cloud, для n8n и claude.ai Project)**: Supabase MCP — те же таблицы.
  Периодическая миграция в локальную БД — `scripts/migrate_jarvis_from_supabase.py --from-supabase`.
- **Инструменты**: MCP серверы (Supabase, Google Drive, Calendar, Gmail, Notion, Firecrawl)
- **Автономные задачи**: n8n (только cron: AI-мониторинг, дайджесты → Telegram push) — пишет в Supabase
- Telegram Bot — только для push-уведомлений от n8n, НЕ для общения

## Базы данных

### Локальный PostgreSQL 17 + pgvector 0.8

#### `jarvis_local`
- `jarvis_memory` — второй мозг (идеи, заметки, задачи, отчёты, эмбеддинги 1536d)
- `jarvis_projects` — контексты проектов
- `jarvis_agent_logs` — аудит действий
- RPC: `match_jarvis_memory()` (совместим с Supabase), `get_jarvis_stats()`,
  `hybrid_search_jarvis_memory()` (BM25+cosine RRF, локальное расширение).
- Материализованная FTS-колонка `fts` (русская морфология) — для гибридного поиска.
- Схема: `db/jarvis-schema.sql` (идемпотентна, без RLS — доступ через ОС).

#### `expertise_ntd` (источник истины НТД для всех проектов на машине)
- `ntd_documents` (395), `clause_vectors` (90 368, vector(1536), HNSW)
- RPC: `match_clauses()`, `hybrid_search_clauses()`, `fts_only_search_clauses()`
- Схема: `PROGRAMMING/expertise-orchestrator/db/ntd-schema.sql`.

### Supabase (проект: omykcphkzmmqpwswwfsw) — cloud-зеркало
- Те же таблицы что выше + `documents` (166, RAG-Consultant), `agsk_catalog` (233 966).
- Используется n8n-воркфлоу и claude.ai Project; локально мы из неё периодически синхронизируем.

## Ключевые файлы
- `JARVIS_SYSTEM_PROMPT.md` — системный промпт для Claude Project на claude.ai
- `JARVIS_CONCEPT.md` — детальный концепт (справочный)
- `db/jarvis-schema.sql` — схема для локального PG (применять: `psql jarvis_local -f db/jarvis-schema.sql`)
- `db/REDIRECT.md` — карта Supabase → local: какие файлы редиректить, какие нет
- `scripts/setup_supabase.sql` — облачная схема (для Supabase, версия RLS+service_role)
- `n8n_workflows/` — workflow для автономных задач
  - `JARVIS_AI_Monitor.json` — ежедневный AI-дайджест (03:00 UTC)
  - `JARVIS_YouTube_Monitor.json` — еженедельный анализ YouTube + синтез идей (пятница 09:00 UTC)
  - `JARVIS_Notion_Sync.json` — синхронизация Notion → Supabase (02:00 UTC)
  - `JARVIS_Voice_Search.json` — поиск по памяти для ElevenLabs агента

## Воркспейс `/Users/kairat/Claude Code/` — карта проектов

JARVIS является центральным оркестратором для всех проектов в этой папке.
Полная карта с описаниями — в memory: `reference_claude_code_workspace.md`.

### Экспертиза ПД (core)
- `PROGRAMMING/expertise-orchestrator/` — multi-agent CLI (31 агент); `npm run poc -- agent:file.pdf`
- `АГСК-3/` — проверка спецификаций на коды АГСК-3; делегат agsk-агента
- `InSmart AGSK-3/` — веб-платформа формирования спецификаций (FastAPI + SQLite)
- `КРАКЕН/` — аудит ПД на Anthropic Managed Agents
- `Заключение/` — генератор КВЭ-заключений (.docx шаблоны)
- `PROGRAMMING/expertise-projects/` — десктоп-учёт объектов экспертизы
- `PROGRAMMING/fire-category-kz/` — калькулятор категорий пожарной опасности (РК)
- `анализ проектов/` — WAT-агент анализа ПД

### НТД, ИРД и документы
- `ntd-qdrant-mcp/` — MCP-сервер НТД-поиска (Qdrant + BGE-M3 + rerank)
- `ИРД выписка/` — WAT-агент выписок ИРД
- `vypiska_ird/` (внутри JARVIS ASSISTANT) — десктоп-приложение batch-выписок ИРД

### Инструменты и инфраструктура
- `Claude Assistant/` — 25+ навыков исполнительного помощника
- `FIRECRAWL/` — веб-скрейпинг для AI-мониторинга
- `N8N-Builder/` — n8n workflow builder
- `Excalidraw Diagram/`, `Excalidraw Visuals/` — диаграммы и визуалы
- `Revit/` — WAT-агент для Revit
- `Video Course/` — VideoForge CLI (video full cycle)

### Архив
- `ARHIVE/` — устаревшие версии проектов (не трогать без явного запроса)

## Claude Code Skills (.claude/skills/)

### Superpowers (obra/superpowers — установлены 2026-04-22)
Обязательный workflow: brainstorming → writing-plans → subagent-driven-development → requesting-code-review → verification-before-completion

- `using-superpowers/` — точка входа, форсирует использование нужного скилла перед любым ответом
- `brainstorming/` — дизайн и спека ПЕРЕД кодом (HARD-GATE: нельзя кодить без одобрения дизайна)
- `writing-plans/` — детальный план реализации с TDD (заменил ai-maestro planning/)
- `subagent-driven-development/` — параллельные субагенты на каждый task + code review
- `dispatching-parallel-agents/` — форсирует параллельность для независимых задач
- `executing-plans/` — inline-выполнение плана с чекпоинтами
- `test-driven-development/` — RED-GREEN-REFACTOR, обязательно до написания кода
- `systematic-debugging/` — root-cause tracing, condition-based waiting
- `using-git-worktrees/` — изолированные worktree per-feature
- `requesting-code-review/` — двухэтапное code review (spec compliance + quality)
- `receiving-code-review/` — как принимать и применять review
- `finishing-a-development-branch/` — финализация ветки, merge/PR workflow
- `verification-before-completion/` — нельзя объявить задачу выполненной без проверки
- `writing-skills/` — TDD-подход к созданию скиллов (обновлён до Superpowers-версии)

### AI & Память
- `memory-search/` — ai-maestro: семантический поиск в памяти
- `agent-management/` — ai-maestro: управление агентами
- `planning-with-files/` — планирование с файлами (task_plan.md, progress.md)

### Разработка
- `senior-prompt-engineer/` — промт-инжиниринг, оптимизация промптов
- `n8n-workflow-patterns/` — паттерны n8n workflow
- `skill-creator/` — создание новых скиллов (нет аналога в Superpowers, оставлен)
- `notion/` — Notion API (2025-09-03 + data_sources), формулы 2.0, подводные камни (let+date, parseDate vs fromTimestamp), праздники РК для working-day формул

### Документы & Контент
- `pdf-processing-pro/` — OCR, таблицы, формы из PDF
- `pptx-official/` — создание PowerPoint презентаций
- `marp-slide/` — Markdown → слайды (темы, CSS)
- `notion-knowledge-capture/` — захват знаний в Notion

### Письмо & Копирайтинг
- `writing-clearly-and-concisely/` — правила Странка для ясной прозы (документация, commit-сообщения, отчёты)
- `humanizer/` — убирает признаки AI-писанины (em-dash overuse, rule-of-three, AI-vocab)
- `copywriting/` — маркетинговый копирайтинг для страниц (homepage, landing, pricing, feature)
- `content-creator/` — SEO-оптимизированный контент с brand voice (блог-посты, соцсети, контент-календарь)
- `speechwriter/` — спичрайтинг: YouTube-сценарии, keynote, питчи, NIW statement, reference letters

### Медиа
- `transcribe/` — транскрибация аудио/видео (scripts/transcribe_diarize.py)
- `speech/` — TTS синтез речи (scripts/text_to_speech.py)

## Правила
1. Все идеи и заметки ОБЯЗАТЕЛЬНО сохранять в jarvis_memory
2. Каждую идею оценивать количественно (feasibility + impact)
3. Действия логировать в jarvis_agent_logs
4. По нормам — СНАЧАЛА искать в базе НТД
5. n8n только для автономных cron-задач, НЕ для интерфейса
6. Все промпты (написание, правки, поиск) — в `Промты для Claude/`, не в других проектах

## Извлечение текста из PDF — трёхуровневый waterfall
Фиксированный порядок, пропуск уровней запрещён:
1. **pdfplumber** — текстовый слой PDF
2. **PaddleOCR-VL-1.5** — единственный допустимый OCR-движок (сканы, фото, чертежи)
3. **Claude Vision** — fallback, только при провале уровня 2

Запрещены альтернативы: tesseract/pytesseract, EasyOCR, doctr, Surya, PaddleOCR < 1.5.
Claude Vision не может быть OCR первого выбора и не может вызываться в обход PaddleOCR.
Каждая эскалация на уровень 3 логируется в `jarvis_agent_logs` с причиной.

Код: `vypiska_ird/ird_extract/ocr_waterfall.py` (публичный API — `extract_pdf()`).
Документация: `.claude/skills/pdf-processing-pro/OCR.md`.

## Работа с Notion (формулы, API, свойства баз)
Первоисточник документации: **https://www.notion.com/help** — сверяться ДО экспериментов с синтаксисом формул, версиями API и типами свойств. API-референс: https://developers.notion.com.

Практические ограничения, подтверждённые на проекте «Проекты Экспертиза» (2026-04-24):
- **API endpoint:** для PATCH свойств базы использовать `/v1/data_sources/{ds_id}` с заголовком `Notion-Version: 2025-09-03`. Старый `/v1/databases/{id}` в этой версии для свойств не работает. `ds_id` получается через `GET /v1/databases/{id}` → `data_sources[0].id`.
- **`let()` в формулах 2.0:** НЕ биндить date-типизированные выражения (`prop("дата")`, `dateBetween(...)`). Результат — `Type error with formula`. Обход: инлайнить даты и dateBetween-результаты в каждое место использования.
- **Константы-даты:** `parseDate("YYYY-MM-DD")` несовместим с prop-date при сравнении через `dateBetween` (разные типы). Использовать `fromTimestamp(ms)` — совместим.
- **Идемпотентность PATCH:** повторный запрос с теми же именами свойств не дублирует — обновляет. Проверять существование перед добавлением новых свойств полезно для логов.

Скрипты (добавление/обновление свойств БД):
- `scripts/notion_add_project_fields.py` — 6 полей в «Проекты Экспертиза» (URL, Select, Formula).
- `scripts/notion_update_expertise_workdays.py` — формула рабочих дней с 14 праздниками РК 2026. При смене года обновлять `RK_HOLIDAYS_2026`.

Токен и Database ID — в `.env`: `NOTION_TOKEN`, `NOTION_DATABASE_ID`.

## Интерактивные дашборды
**Все запросы на дашборды, панели, KPI-экраны, визуализацию данных, аналитические отчёты** выполняются скиллом **`dashboard-builder`** (`.claude/skills/dashboard-builder/`).

Триггеры: «дашборд», «панель», «аналитика», «KPI», «визуализация», «BI-отчёт» / dashboard, analytics, monitoring, KPI screen.

Workflow:
1. Скилл `dashboard-builder` — точка входа.
2. Mode: **single-html** (по умолчанию, HTML-артефакт) / **next-shadcn** (приложение) / **quarto** (отчёт).
3. Тема: claude-light / zinc-dark / executive / realtime-ops.
4. Движок по умолчанию — **ECharts 5.6** (CDN). Recharts — только для next-shadcn.
5. Готовые `.html` сохранять в `JARVIS ASSISTANT/` под именем `<topic>_<YYYY-MM-DD>.html`.

## Регистрация ресурсов в ЕШДИ (ППРК №832)
Для доступа с рабочих мест Госэкспертизы ресурс должен: (а) хоститься в РК со статическим IP, (б) пройти проверку в ЕШДИ.

- **Проверка доступа:** https://checkip.sts.kz/ — ввести домен, без ЭЦП. Если «Доступ разрешён» — регистрация не нужна.
- **Регистрация (если блок):** https://support.sts.kz/registration → ЭЦП через NCALayer → «ЕШДИ» → «Открытие доступа к ресурсу». Срок: 3–10 рабочих дней.
- **Запасной путь без ЭЦП юрлица:** служебная записка в IT-отдел Госэкспертизы — шаблон `scripts/agsk3_eshdi_request.md`.
- **Действующие ресурсы:** `agsk-3.baikulov-k-i.kz` (VPS hoster.kz, `185.129.49.42`, Астана).
- **Шаблоны и чек-листы:** `scripts/agsk3_migration_checklist.md` (миграция на `.kz`), `scripts/vps_setup_steps.md` (nginx + Let's Encrypt).
- **Подробная процедура и поля заявки:** см. auto-memory `reference_eshdi_registration.md`.
