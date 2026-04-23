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
  - `JARVIS_AI_Monitor.json` — ежедневный AI-дайджест (03:00 UTC)
  - `JARVIS_YouTube_Monitor.json` — еженедельный анализ YouTube + синтез идей (пятница 09:00 UTC)
  - `JARVIS_Notion_Sync.json` — синхронизация Notion → Supabase (02:00 UTC)
  - `JARVIS_Voice_Search.json` — поиск по памяти для ElevenLabs агента

## Связанные проекты (G:\Мой диск\AI\Claude Code\)
- `PROMT/` — **единое хранилище промптов**: написание, корректировка, рефакторинг всех промптов выполняется здесь
- `RAG-Consultant/` — Supabase SQL-паттерны, RAG pipeline
- `Claude Assistant/` — 25+ навыков, промпты инженерных агентов
- `n8n-mcp/` — MCP-сервер для n8n автоматизации
- `FIRECRAWL/` — веб-скрейпинг для AI-мониторинга

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
6. Все промпты (написание, правки, поиск) — в `G:\Мой диск\AI\Claude Code\PROMT`, не в других проектах

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

## Регистрация ресурсов в ЕШДИ (ППРК №832)
Для доступа с рабочих мест Госэкспертизы ресурс должен: (а) хоститься в РК со статическим IP, (б) пройти проверку в ЕШДИ.

- **Проверка доступа:** https://checkip.sts.kz/ — ввести домен, без ЭЦП. Если «Доступ разрешён» — регистрация не нужна.
- **Регистрация (если блок):** https://support.sts.kz/registration → ЭЦП через NCALayer → «ЕШДИ» → «Открытие доступа к ресурсу». Срок: 3–10 рабочих дней.
- **Запасной путь без ЭЦП юрлица:** служебная записка в IT-отдел Госэкспертизы — шаблон `scripts/agsk3_eshdi_request.md`.
- **Действующие ресурсы:** `agsk-3.baikulov-k-i.kz` (VPS hoster.kz, `185.129.49.42`, Астана).
- **Шаблоны и чек-листы:** `scripts/agsk3_migration_checklist.md` (миграция на `.kz`), `scripts/vps_setup_steps.md` (nginx + Let's Encrypt).
- **Подробная процедура и поля заявки:** см. auto-memory `reference_eshdi_registration.md`.
