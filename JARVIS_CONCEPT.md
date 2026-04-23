# JARVIS — Персональный AI-оркестратор

## Философия проекта

> «Ты не нанимаешь людей. Ты оцифровываешь себя и создаёшь армию агентов.»

JARVIS — это система персонального AI-оркестратора, превращающая поток сознания пользователя (голос, текст, идеи) в конкретные действия через армию специализированных AI-агентов. Центральный ассистент понимает контекст, классифицирует входящий поток, маршрутизирует задачи и координирует работу агентов.

### Ключевые принципы

1. **Один вход — множество выходов**: пользователь говорит одну мысль → система сама определяет, что с ней делать
2. **Второй мозг**: вся история, контексты, решения хранятся и доступны агентам
3. **No-humans бизнес**: максимальная автоматизация без найма людей
4. **Модульность**: каждый агент — независимый модуль, который можно добавить/заменить/отключить

---

## Архитектура системы

### Общая структура

```
┌─────────────┐     ┌──────────────────────────┐     ┌─────────────────────────┐
│   ВХОД      │     │     JARVIS CORE          │     │    АРМИЯ АГЕНТОВ       │
│             │     │                          │     │                         │
│  Телефон    │────▶│  1. Оркестратор (Claude) │────▶│  Инженерные агенты     │
│  Claude App │     │  2. Второй мозг (Supa)   │     │  Контент-агенты        │
│  Telegram   │     │  3. Классификатор        │     │  Бизнес-агенты         │
│  Webhook    │     │  4. Роутер (n8n)         │     │  Мониторинг-агенты     │
│             │     │                          │     │  Утилитарные агенты    │
└─────────────┘     └──────────────────────────┘     └─────────────────────────┘
                              │                                   │
                    ┌─────────▼───────────┐             ┌────────▼──────────┐
                    │   ИНСТРУМЕНТЫ       │             │   ВЫХОДЫ          │
                    │   (MCP серверы)      │             │                   │
                    │                     │             │  Telegram-отчёты  │
                    │  Google Drive       │             │  Excel-файлы      │
                    │  GitHub             │             │  YouTube-контент  │
                    │  Supabase           │             │  Email-рассылки   │
                    │  Notion             │             │  GitHub commits   │
                    │  Calendar           │             │  Notion-записи    │
                    │  Gmail              │             │                   │
                    └─────────────────────┘             └───────────────────┘
```

---

## Слой 1: Вход (Input Layer)

### Основной канал: Claude Mobile App

Пользователь открывает Claude на телефоне и говорит/пишет всё, что приходит в голову:

- «У меня идея — сделать калькулятор категории пожарной опасности зданий»
- «Проверь проект ПСД по объекту Жанаозен, там что-то с SF6 датчиками»
- «Запиши — нужно записать видео про автоматизацию АГСК-3»
- «Какой статус по патенту?»

### Альтернативные каналы (расширение)

| Канал | Назначение | Технология |
|-------|-----------|------------|
| Telegram Bot | Быстрые команды, уведомления | n8n + Telegram Bot API |
| Webhook API | Интеграция с внешними системами | n8n webhook node |
| Email → JARVIS | Пересылка писем для обработки | Gmail MCP + n8n trigger |
| Voice memo | Голосовые заметки (файлы) | Whisper API → текст → JARVIS |
| Claude Code CLI | Прямые технические задачи | Claude Code terminal |

---

## Слой 2: JARVIS Core (Мозг)

### 2.1 Оркестратор

**Роль**: Центральный координатор, который понимает контекст и принимает решения.

**Технология**: Claude API (Opus для сложных решений, Sonnet для рутины)

**Системный промпт оркестратора** (CLAUDE.md для проекта):

```markdown
# JARVIS Orchestrator System Prompt

Ты — JARVIS, персональный AI-оркестратор инженера пожарной безопасности Кайрата.

## Твои задачи:
1. Принимать входящий поток (голос/текст) от пользователя
2. Классифицировать каждое сообщение по типу
3. Извлекать actionable items
4. Маршрутизировать задачи соответствующим агентам
5. Отслеживать статусы и докладывать результаты

## Типы входящих сообщений:
- IDEA: Идея для будущей реализации → сохранить в банк идей + оценить потенциал
- TASK: Конкретная задача → определить агента и запустить
- NOTE: Заметка/мысль → сохранить во второй мозг
- QUERY: Вопрос → ответить из базы знаний или найти информацию
- STATUS: Запрос статуса → собрать отчёт от агентов
- STREAM: Поток сознания → извлечь полезное, остальное сохранить

## Формат ответа классификации (JSON):
{
  "type": "IDEA|TASK|NOTE|QUERY|STATUS|STREAM",
  "summary": "краткое описание",
  "priority": "critical|high|medium|low",
  "agents": ["agent_id_1", "agent_id_2"],
  "actions": [
    {
      "agent": "agent_id",
      "action": "описание действия",
      "params": {}
    }
  ],
  "save_to_memory": true,
  "memory_tags": ["tag1", "tag2"]
}
```

### 2.2 Второй мозг (Memory Layer)

**Технология**: Supabase + pgvector (уже развёрнут)

**Структура таблиц**:

```sql
-- Основная таблица памяти
CREATE TABLE jarvis_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    content_type TEXT NOT NULL, -- idea, task, note, decision, context
    summary TEXT,
    tags TEXT[],
    embedding VECTOR(1536), -- text-embedding-3-small
    source TEXT, -- voice, text, agent_report, auto
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'active', -- active, archived, completed, dismissed
    related_project TEXT, -- привязка к проекту
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Банк идей с оценкой
CREATE TABLE jarvis_ideas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID REFERENCES jarvis_memory(id),
    title TEXT NOT NULL,
    description TEXT,
    feasibility_score INTEGER, -- 1-10
    impact_score INTEGER, -- 1-10
    effort_estimate TEXT, -- hours/days/weeks
    status TEXT DEFAULT 'new', -- new, evaluating, planned, in_progress, done, dismissed
    evaluation_notes TEXT, -- заметки JARVIS по оценке
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Контексты проектов
CREATE TABLE jarvis_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    agents TEXT[], -- какие агенты задействованы
    key_decisions JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Логи действий агентов
CREATE TABLE jarvis_agent_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    status TEXT, -- success, error, pending
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы для быстрого поиска
CREATE INDEX idx_memory_embedding ON jarvis_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_memory_tags ON jarvis_memory USING gin (tags);
CREATE INDEX idx_memory_type ON jarvis_memory (content_type);
CREATE INDEX idx_memory_status ON jarvis_memory (status);
```

### 2.3 Классификатор

**Технология**: Claude API вызов с structured output

```python
# classifier.py — модуль классификации входящего потока

import json
from anthropic import Anthropic

client = Anthropic()

CLASSIFIER_PROMPT = """
Ты — модуль классификации JARVIS.
Проанализируй входящее сообщение пользователя и определи:

1. ТИП: IDEA / TASK / NOTE / QUERY / STATUS / STREAM
2. ПРИОРИТЕТ: critical / high / medium / low
3. ЦЕЛЕВЫЕ АГЕНТЫ: кто должен обработать
4. ДЕЙСТВИЯ: конкретные шаги для каждого агента
5. ТЕГИ: для сохранения в памяти

Контекст пользователя:
- Инженер пожарной безопасности (АПС/СОУЭ)
- Строит AI-автоматизацию инженерных процессов
- Ведёт YouTube канал
- Готовит патент и NIW визу в США
- Текущие проекты: {active_projects}

Ответь ТОЛЬКО валидным JSON.
"""

def classify_input(message: str, active_projects: list[str]) -> dict:
    """Классифицирует входящее сообщение."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=CLASSIFIER_PROMPT.format(
            active_projects=", ".join(active_projects)
        ),
        messages=[{"role": "user", "content": message}]
    )
    return json.loads(response.content[0].text)
```

### 2.4 Роутер агентов

**Технология**: n8n workflows (kairat679.app.n8n.cloud)

```
Основной workflow: JARVIS_Router

Trigger: Webhook / Schedule / Manual
    │
    ▼
Classify Input (Claude API)
    │
    ▼
Switch Node (по типу)
    ├── IDEA → Save to Ideas Bank + Evaluate
    ├── TASK → Route to Agent Workflow
    ├── NOTE → Save to Memory
    ├── QUERY → RAG Search + Answer
    ├── STATUS → Collect Agent Reports
    └── STREAM → Extract & Save
    │
    ▼
Execute Agent Workflow(s)
    │
    ▼
Log Results → Notify User (Telegram)
```

---

## Слой 3: Армия агентов

### Группа A: Инженерные агенты (приоритет 1)

#### A1: АПС/СОУЭ Аналитик

```yaml
agent_id: aps_analyst
description: Анализ проектной документации АПС/СОУЭ на соответствие нормам
technology:
  - RAG over НТД (Supabase + pgvector)
  - Claude API для анализа
  - pdfplumber для парсинга ПД
inputs:
  - PDF проектной документации
  - Текстовые запросы по нормам
outputs:
  - Отчёт о соответствии нормам
  - Список замечаний с ссылками на НТД
  - Excel с таблицей замечаний
capabilities:
  - Проверка ПД на соответствие СП, ГОСТ, СНиП
  - Поиск по базе НТД (300+ документов)
  - Формирование замечаний экспертизы
  - Анализ спецификаций оборудования
n8n_workflow: JARVIS_APS_Analyst
status: 80% ready (RAG работает, нужна обёртка)
```

#### A2: Спецификатор АГСК-3

```yaml
agent_id: agsk_specifier
description: Автоматическая генерация спецификаций из ПД по каталогу АГСК-3
technology:
  - АГСК-3 каталог в Supabase (Markdown)
  - Claude API для маппинга
  - openpyxl для Excel-выхода
inputs:
  - PDF/текст проектной документации
  - Раздел ПД для спецификации
outputs:
  - Excel спецификация по ГОСТ 21.101
  - Отчёт о неопознанных позициях
capabilities:
  - Парсинг ведомостей и таблиц из ПД
  - Сопоставление с АГСК-3 (234,000 записей)
  - Формирование ведомости по ГОСТ
  - Проверка актуальности кодов
n8n_workflow: JARVIS_AGSK_Specifier
status: 60% ready (парсер + каталог есть, нужен pipeline)
```

#### A3: ИРД Экстрактор

```yaml
agent_id: ird_extractor
description: Извлечение данных из исходно-разрешительной документации
technology:
  # Трёхуровневый waterfall извлечения текста (порядок обязателен):
  # 1) pdfplumber → 2) PaddleOCR-VL-1.5 → 3) Claude Vision (fallback)
  - pdfplumber — уровень 1: текстовые PDF с selectable text
  - PaddleOCR-VL-1.5 — уровень 2: единственный OCR-движок для сканов/фото/PDF-изображений/чертежей
  - Claude Vision — уровень 3: fallback, только если PaddleOCR-VL-1.5 не справился (рукопись, сложный layout, низкая уверенность)
  - Шаблоны выписок ИРД
inputs:
  - Сканы/PDF документов ИРД
  - Тип документа (АПЗ, ТУ, акт, постановление)
outputs:
  - Структурированная выписка ИРД
  - Excel/DOCX реестр документов
capabilities:
  - Извлечение текста по waterfall pdfplumber → PaddleOCR-VL-1.5 → Claude Vision
  - Извлечение ключевых полей (номер, дата, орган)
  - Формирование выписки по шаблону
  - Проверка полноты комплекта ИРД
  - Логирование причины перехода на уровень 3 (Claude Vision) в jarvis_agent_logs
n8n_workflow: JARVIS_IRD_Extractor
status: 40% ready (базовый модуль есть)
```

#### A4: Эксперт ПСД

```yaml
agent_id: psd_expert
description: Экспертиза проектно-сметной документации
technology:
  - RAG over НТД + сметные нормативы
  - Claude API для анализа смет
  - openpyxl для обработки смет в Excel
inputs:
  - Сметная документация (Excel/PDF)
  - Проектная документация
outputs:
  - Экспертное заключение
  - Замечания к ПСД
  - Откорректированные сметы
capabilities:
  - Проверка сметных расценок
  - Анализ объёмов работ
  - Сверка с проектными решениями
  - Формирование замечаний эксперта
n8n_workflow: JARVIS_PSD_Expert
status: 30% ready (концепт)
```

### Группа B: Контент и продвижение

#### B1: Контент-менеджер

```yaml
agent_id: content_manager
description: Управление YouTube каналом и контент-планом
technology:
  - Claude API для генерации идей и сценариев
  - YouTube Data API для аналитики
  - Telegram для уведомлений
inputs:
  - Идеи для видео
  - Тренды AI/engineering
  - Аналитика канала
outputs:
  - Контент-план (Notion)
  - Сценарии видео
  - Описания и теги для YouTube
  - Посты для Telegram/LinkedIn
capabilities:
  - Генерация идей для видео на основе трендов
  - Написание сценариев в стиле Nate Herk
  - SEO-оптимизация заголовков и описаний
  - Планирование графика публикаций
  - Анализ конкурентов
n8n_workflow: JARVIS_Content_Manager
status: 20% ready (идея)
```

#### B2: AI-мониторинг

```yaml
agent_id: ai_monitor
description: Мониторинг AI-новостей и обновлений инструментов
technology:
  - Web scraping / RSS
  - Claude API для фильтрации и суммаризации
  - Telegram для дайджестов
inputs:
  - RSS фиды (Anthropic, OpenAI, Google AI, HuggingFace)
  - Twitter/X ключевых фигур
  - GitHub trending
outputs:
  - Ежедневный дайджест в Telegram
  - Еженедельный отчёт с приоритетами
  - Алерты на критические обновления
capabilities:
  - Мониторинг 20+ источников
  - Фильтрация по релевантности (engineering + AI)
  - Суммаризация на русском
  - Выделение actionable items
sources:
  - Anthropic Blog / Changelog
  - OpenAI Blog
  - Google AI Blog
  - HuggingFace Papers
  - ArXiv (cs.AI, cs.SE)
  - GitHub Trending
  - ProductHunt AI категория
  - Нормативные изменения РК (adilet.zan.kz)
n8n_workflow: JARVIS_AI_Monitor
status: 40% ready (n8n дайджест в проектировании)
```

### Группа C: Бизнес и стратегия

#### C1: NIW Трекер

```yaml
agent_id: niw_tracker
description: Отслеживание прогресса по NIW визе и портфолио
technology:
  - Notion для трекинга
  - Google Calendar для дедлайнов
  - Claude API для review документов
inputs:
  - Статусы задач портфолио
  - Документы для review
  - Дедлайны
outputs:
  - Еженедельный статус-отчёт
  - Напоминания о дедлайнах
  - Review документов NIW пакета
capabilities:
  - Трекинг 12-недельного плана
  - Мониторинг GitHub READMEs
  - Проверка портфолио-сайта
  - Напоминание о testimonials
  - Анализ Matter of Dhanasar соответствия
n8n_workflow: JARVIS_NIW_Tracker
status: 20% ready (план есть, автоматизация нет)
```

#### C2: Патентный агент

```yaml
agent_id: patent_agent
description: Управление процессом патентования
technology:
  - Claude API для подготовки документов
  - Google Drive для хранения
  - Calendar для дедлайнов
inputs:
  - Описание изобретения
  - Статусы заявок
  - Корреспонденция с НИИС/USPTO
outputs:
  - Черновики патентных заявок
  - Трекинг статусов
  - Напоминания о сроках
capabilities:
  - Подготовка описания изобретения
  - Формулировка патентных пунктов
  - Мониторинг патентных баз (аналоги)
  - Отслеживание сроков подачи
n8n_workflow: JARVIS_Patent_Agent
status: 15% ready (стратегия разработана)
```

#### C3: Бизнес-аналитик

```yaml
agent_id: biz_analyst
description: Анализ рынка и конкурентов
technology:
  - Web search
  - Claude API для анализа
  - Notion для отчётов
inputs:
  - Запросы на исследование рынка
  - Информация о конкурентах
outputs:
  - Аналитические отчёты
  - Конкурентный анализ
  - Рыночные возможности
capabilities:
  - Мониторинг конкурентов (Jensen Hughes, Arup, WSP, etc.)
  - Анализ рынка AI в строительстве
  - Оценка бизнес-моделей
  - Поиск потенциальных клиентов/партнёров
n8n_workflow: JARVIS_Biz_Analyst
status: 10% ready (концепт)
```

### Группа D: Утилитарные агенты

#### D1: Разработчик

```yaml
agent_id: developer
description: Автоматизация задач разработки через Claude Code
technology:
  - Claude Code CLI
  - GitHub API
  - VS Code integration
inputs:
  - Технические задания
  - Баг-репорты
  - Feature requests
outputs:
  - Code commits
  - Pull requests
  - Документация
capabilities:
  - Написание кода по спецификации
  - Code review
  - Рефакторинг
  - Тестирование (TDD workflow)
  - Обновление README
n8n_workflow: JARVIS_Developer
status: 50% ready (Claude Code + CLAUDE.md работают)
```

#### D2: Продажи и Outreach

```yaml
agent_id: sales_outreach
description: Автоматизация холодных контактов и продаж
technology:
  - Gmail MCP
  - LinkedIn API (через browser automation)
  - Claude API для персонализации
inputs:
  - Список целевых компаний/контактов
  - Шаблоны писем
  - Информация о продукте
outputs:
  - Персонализированные письма
  - Отслеживание ответов
  - CRM-записи (Notion)
capabilities:
  - Генерация персонализированных cold emails
  - A/B тестирование тем писем
  - Follow-up последовательности
  - Трекинг конверсий
n8n_workflow: JARVIS_Sales
status: 5% ready (будущее расширение)
```

#### D3: Поддержка клиентов

```yaml
agent_id: support
description: Автоматические ответы на запросы клиентов
technology:
  - Telegram Bot / Email
  - RAG по документации продукта
  - Claude API
inputs:
  - Вопросы клиентов
  - Тикеты поддержки
outputs:
  - Ответы клиентам
  - FAQ обновления
  - Эскалация сложных запросов
capabilities:
  - Автоответы на типовые вопросы
  - Поиск по документации
  - Создание тикетов
  - Эскалация к пользователю
n8n_workflow: JARVIS_Support
status: 5% ready (будущее расширение)
```

---

## Слой 4: Инструменты и интеграции (MCP Layer)

### Текущие подключения (готовы)

| MCP сервер | Статус | Использование |
|-----------|--------|--------------|
| Google Drive | Подключён | НТД база, документы проектов |
| Google Calendar | Подключён | Дедлайны, встречи |
| Gmail | Подключён | Переписка, outreach |
| Notion | Подключён | Трекинг задач, контент-план |
| Supabase | Подключён | Второй мозг, RAG, логи |
| n8n | Подключён | Оркестрация workflows |
| GitHub | Доступен | Репозитории, CI/CD |
| Excalidraw | Подключён | Визуализация архитектуры |

### Планируемые интеграции

| Интеграция | Назначение | Приоритет |
|-----------|-----------|-----------|
| Telegram Bot API | Основной канал уведомлений | Высокий |
| YouTube Data API | Аналитика канала | Средний |
| ElevenLabs API | TTS для видео (VideoForge) | Средний |
| Brave Search API | Веб-поиск агентами | Высокий |
| Deepgram API | STT для голосовых заметок | Средний |
| LinkedIn API | Professional outreach | Низкий |
| Adilet.zan.kz | Мониторинг нормативов РК | Средний |

---

## План реализации

### Фаза 0: Фундамент (Неделя 1-2)

```
Цель: Развернуть базовую инфраструктуру JARVIS

Задачи:
□ Создать Supabase таблицы (jarvis_memory, jarvis_ideas, jarvis_projects, jarvis_agent_logs)
□ Написать модуль classifier.py
□ Создать базовый n8n workflow JARVIS_Router
□ Настроить Telegram Bot для уведомлений
□ Написать CLAUDE.md для проекта JARVIS

Результат: Можно отправить текст → получить классификацию → сохранить в память
```

### Фаза 1: Первый агент (Неделя 3-4)

```
Цель: Полноценный АПС/СОУЭ Аналитик

Задачи:
□ Обернуть существующий RAG в API endpoint
□ Создать n8n workflow JARVIS_APS_Analyst
□ Подключить к роутеру
□ Добавить генерацию Excel-отчётов
□ Тестирование на реальных проектах

Результат: "Проверь проект X на соответствие СП 484" → отчёт в Telegram
```

### Фаза 2: Спецификатор + ИРД (Неделя 5-8)

```
Цель: Запустить два инженерных агента

Задачи:
□ Завершить pipeline АГСК-3
□ Создать API для спецификатора
□ Развернуть ИРД экстрактор
□ Интеграция с Google Drive (автозагрузка ПД)
□ Связать все инженерные агенты через роутер

Результат: Загрузил PDF → получил спецификацию + выписку ИРД
```

### Фаза 3: Контент + Мониторинг (Неделя 9-12)

```
Цель: Автоматизация контента и AI-мониторинга

Задачи:
□ Запустить ежедневный AI-дайджест
□ Создать контент-план в Notion
□ Автоматизация генерации сценариев
□ SEO-оптимизатор для YouTube

Результат: Утренний дайджест + автоматический контент-план
```

### Фаза 4: Бизнес-агенты (Неделя 13-16)

```
Цель: NIW трекер + патентный агент

Задачи:
□ Автоматизация трекинга NIW плана
□ Мониторинг патентных баз
□ Бизнес-аналитик (конкуренты)
□ Начальный outreach

Результат: Еженедельный NIW-отчёт + алерты по патенту
```

### Фаза 5: Масштабирование (Неделя 17+)

```
Цель: Полная автономность системы

Задачи:
□ Агент продаж и outreach
□ Автоматическая поддержка клиентов
□ Self-healing (автоматическое исправление ошибок)
□ Аналитический дашборд (React)
□ Voice-first interface (полностью голосовое управление)
```

---

## Технический стек

### Core

```
Runtime:        Python 3.12 + Node.js 20
LLM:            Claude API (Opus 4 для оркестратора, Sonnet 4 для агентов)
Vector DB:      Supabase pgvector (text-embedding-3-small)
Orchestration:  n8n (kairat679.app.n8n.cloud)
Storage:        Google Drive + Supabase Storage
State:          Supabase PostgreSQL
```

### Инфраструктура

```
Сервер:         VPS (Hetzner/DigitalOcean) или Alem.Cloud
CI/CD:          GitHub Actions
Monitoring:     n8n execution logs + custom dashboards
Secrets:        .env files / Supabase Vault
```

### Разработка

```
IDE:            VS Code + Claude Code
Workflow:       TDD (RED→GREEN→REFACTOR→COMMIT)
VCS:            GitHub
CLAUDE.md:      Обязательный для каждого модуля
```

---

## Структура проекта для Claude Code

```
jarvis/
├── CLAUDE.md                    # Глобальные инструкции
├── README.md                    # Документация проекта
├── pyproject.toml               # Python зависимости
├── package.json                 # Node.js зависимости
│
├── core/                        # Ядро JARVIS
│   ├── CLAUDE.md               # Инструкции для core модуля
│   ├── orchestrator.py         # Главный оркестратор
│   ├── classifier.py           # Классификатор входа
│   ├── router.py               # Роутер агентов
│   ├── memory.py               # Работа с вторым мозгом
│   └── config.py               # Конфигурация
│
├── agents/                      # Агенты
│   ├── CLAUDE.md               # Инструкции для агентов
│   ├── base_agent.py           # Базовый класс агента
│   ├── aps_analyst/            # АПС/СОУЭ Аналитик
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── tests/
│   ├── agsk_specifier/         # Спецификатор АГСК-3
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   ├── parser.py
│   │   ├── matcher.py
│   │   └── tests/
│   ├── ird_extractor/          # ИРД Экстрактор
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   └── tests/
│   ├── content_manager/        # Контент-менеджер
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   └── tests/
│   ├── ai_monitor/             # AI Мониторинг
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   ├── sources.py
│   │   └── tests/
│   ├── niw_tracker/            # NIW Трекер
│   │   ├── CLAUDE.md
│   │   ├── agent.py
│   │   └── tests/
│   └── patent_agent/           # Патентный агент
│       ├── CLAUDE.md
│       ├── agent.py
│       └── tests/
│
├── integrations/               # Интеграции
│   ├── CLAUDE.md
│   ├── telegram_bot.py         # Telegram Bot
│   ├── supabase_client.py      # Supabase клиент
│   ├── gdrive_client.py        # Google Drive
│   ├── n8n_client.py           # n8n API
│   └── youtube_client.py       # YouTube API
│
├── api/                        # API сервер
│   ├── CLAUDE.md
│   ├── main.py                 # FastAPI сервер
│   ├── routes/
│   │   ├── input.py            # Приём входящих
│   │   ├── agents.py           # Управление агентами
│   │   ├── memory.py           # Доступ к памяти
│   │   └── status.py           # Статус системы
│   └── middleware/
│       ├── auth.py
│       └── logging.py
│
├── n8n_workflows/              # Экспорт n8n workflows
│   ├── JARVIS_Router.json
│   ├── JARVIS_APS_Analyst.json
│   ├── JARVIS_AGSK_Specifier.json
│   ├── JARVIS_AI_Monitor.json
│   └── ...
│
├── scripts/                    # Утилиты
│   ├── setup_supabase.sql      # SQL для создания таблиц
│   ├── seed_memory.py          # Начальное наполнение памяти
│   ├── migrate.py              # Миграции БД
│   └── healthcheck.py          # Проверка здоровья системы
│
├── tests/                      # Тесты
│   ├── conftest.py
│   ├── test_classifier.py
│   ├── test_router.py
│   └── test_memory.py
│
└── docs/                       # Документация
    ├── architecture.md         # Эта документация
    ├── agents_guide.md         # Как создавать новых агентов
    ├── api_reference.md        # API документация
    └── deployment.md           # Инструкция по деплою
```

---

## Базовый класс агента (шаблон)

```python
# agents/base_agent.py

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
import json
from anthropic import Anthropic
from core.memory import MemoryManager

class BaseAgent(ABC):
    """Базовый класс для всех агентов JARVIS."""

    def __init__(self, agent_id: str, name: str, model: str = "claude-sonnet-4-20250514"):
        self.agent_id = agent_id
        self.name = name
        self.model = model
        self.client = Anthropic()
        self.memory = MemoryManager()

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Системный промпт агента."""
        pass

    @abstractmethod
    def execute(self, task: dict) -> dict:
        """Выполнить задачу. Возвращает результат."""
        pass

    def think(self, prompt: str, context: str = "") -> str:
        """Отправить запрос к LLM."""
        messages = [{"role": "user", "content": prompt}]
        if context:
            messages[0]["content"] = f"Контекст:\n{context}\n\nЗадача:\n{prompt}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.get_system_prompt(),
            messages=messages
        )
        return response.content[0].text

    def search_memory(self, query: str, limit: int = 5) -> list[dict]:
        """Поиск в памяти JARVIS."""
        return self.memory.semantic_search(query, limit=limit)

    def save_to_memory(self, content: str, content_type: str, tags: list[str]):
        """Сохранить в память JARVIS."""
        self.memory.save(
            content=content,
            content_type=content_type,
            tags=tags,
            source=f"agent:{self.agent_id}"
        )

    def log_action(self, action: str, input_data: Any, output_data: Any, status: str):
        """Логировать действие агента."""
        self.memory.log_agent_action(
            agent_id=self.agent_id,
            action=action,
            input_data=input_data,
            output_data=output_data,
            status=status
        )

    def report(self) -> dict:
        """Сформировать отчёт о состоянии агента."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": "active",
            "last_action": self.memory.get_last_action(self.agent_id),
            "timestamp": datetime.now().isoformat()
        }
```

---

## Пример реализации агента

```python
# agents/aps_analyst/agent.py

from agents.base_agent import BaseAgent
from integrations.supabase_client import SupabaseRAG

class APSAnalystAgent(BaseAgent):
    """Агент анализа проектной документации АПС/СОУЭ."""

    def __init__(self):
        super().__init__(
            agent_id="aps_analyst",
            name="АПС/СОУЭ Аналитик",
            model="claude-sonnet-4-20250514"
        )
        self.rag = SupabaseRAG(collection="ntd_documents")

    def get_system_prompt(self) -> str:
        return """
Ты — эксперт по пожарной безопасности, специализирующийся на системах АПС и СОУЭ.

Твои задачи:
1. Анализировать проектную документацию на соответствие нормам РК
2. Находить нарушения и несоответствия
3. Формировать замечания со ссылками на конкретные пункты НТД
4. Предлагать решения по устранению замечаний

Нормативная база:
- СП РК 5.02-107 (Системы пожарной сигнализации)
- СП РК 5.02-108 (Системы оповещения и управления эвакуацией)
- ГОСТ 34701-2020
- СН РК 2.02-11 (Пожарная безопасность зданий)

При анализе:
- Указывай конкретный пункт нормы
- Объясняй суть нарушения
- Предлагай вариант исправления
- Оценивай критичность: critical / major / minor
"""

    def execute(self, task: dict) -> dict:
        """Анализ ПД на соответствие нормам."""
        document_text = task.get("document_text", "")
        query = task.get("query", "Проверить на соответствие нормам")

        # 1. Поиск релевантных норм
        relevant_norms = self.rag.search(query, limit=10)

        # 2. Формирование контекста
        norms_context = "\n\n".join([
            f"### {norm['title']}\n{norm['content']}"
            for norm in relevant_norms
        ])

        # 3. Анализ
        analysis_prompt = f"""
Проанализируй следующий фрагмент проектной документации:

--- ДОКУМЕНТ ---
{document_text[:8000]}
--- КОНЕЦ ДОКУМЕНТА ---

Используй следующие нормы для проверки:

--- НОРМАТИВНАЯ БАЗА ---
{norms_context}
--- КОНЕЦ НОРМАТИВНОЙ БАЗЫ ---

Запрос: {query}

Ответь в формате JSON:
{{
  "summary": "общий вывод",
  "violations": [
    {{
      "severity": "critical|major|minor",
      "norm_reference": "СП XX п.X.X.X",
      "description": "описание нарушения",
      "recommendation": "рекомендация по устранению",
      "document_location": "где в документе"
    }}
  ],
  "compliant_items": ["что соответствует нормам"],
  "recommendations": ["дополнительные рекомендации"]
}}
"""

        result = self.think(analysis_prompt)

        # 4. Логирование
        self.log_action(
            action="analyze_pd",
            input_data={"query": query, "doc_length": len(document_text)},
            output_data=result,
            status="success"
        )

        # 5. Сохранение в память
        self.save_to_memory(
            content=f"Анализ ПД: {query}\nРезультат: {result[:500]}",
            content_type="agent_report",
            tags=["aps", "analysis", "psd"]
        )

        return {"agent": self.agent_id, "result": result}
```

---

## Главный CLAUDE.md для проекта

```markdown
# JARVIS Project — CLAUDE.md

## Проект
JARVIS — персональный AI-оркестратор для автоматизации инженерных и бизнес-процессов.

## Обязательные правила
1. TDD workflow: RED → GREEN → REFACTOR → COMMIT
2. Все агенты наследуют BaseAgent
3. Каждый модуль имеет свой CLAUDE.md
4. Логирование всех действий агентов в jarvis_agent_logs
5. Все промпты хранятся в отдельных файлах prompts.py
6. Type hints обязательны
7. Docstrings на русском языке
8. Тесты покрывают happy path + edge cases

## Технический контекст
- Python 3.12, FastAPI, Anthropic SDK
- Supabase (PostgreSQL + pgvector)
- n8n для оркестрации workflows
- Claude Opus для оркестратора, Sonnet для агентов
- Embeddings: text-embedding-3-small (1536 dims)

## Команды
- `pytest` — запуск тестов
- `uvicorn api.main:app --reload` — запуск API
- `python scripts/healthcheck.py` — проверка системы

## Структура
Смотри docs/architecture.md для полной архитектуры.

## Приоритеты разработки
1. Core (orchestrator, classifier, memory)
2. Инженерные агенты (APS, AGSK, IRD)
3. Контент и мониторинг
4. Бизнес-агенты
```

---

## Варианты расширения и модернизации

### Краткосрочные (1-3 мес.)

1. **Voice-first интерфейс**: Подключить Deepgram/Whisper для прямого голосового ввода через Telegram voice messages → STT → JARVIS → TTS → голосовой ответ
2. **Дашборд**: React-приложение для визуализации состояния всех агентов, памяти, идей
3. **Self-healing**: Агенты автоматически перезапускаются при ошибках, уведомляют о проблемах
4. **Multi-modal input**: Фото/скан/PDF чертежей → waterfall извлечения текста: (1) pdfplumber для текстовых PDF → (2) PaddleOCR-VL-1.5 для сканов и изображений → (3) Claude Vision как fallback, если PaddleOCR-VL-1.5 не справился. Claude Vision параллельно используется для визуального анализа схемы (компоненты, связи, символы), но не как OCR первого выбора.

### Среднесрочные (3-6 мес.)

5. **Агентская сеть**: Агенты общаются друг с другом напрямую (A2A protocol от Google)
6. **Qwen fallback**: Для русскоязычных задач с низким приоритетом использовать Qwen через Alem.Cloud (экономия токенов)
7. **Автономный режим**: JARVIS сам инициирует задачи по расписанию (утренний briefing, вечерний отчёт, еженедельный review)
8. **Knowledge graph**: Поверх pgvector добавить граф связей между сущностями (проекты ↔ нормы ↔ замечания ↔ решения)

### Долгосрочные (6-12 мес.)

9. **White-label платформа**: Превратить JARVIS в SaaS для других инженеров пожарной безопасности
10. **Marketplace агентов**: Другие пользователи могут создавать и подключать своих агентов
11. **Digital twin компании**: Полная цифровая модель бизнес-процессов, JARVIS управляет всем
12. **AR/VR интеграция**: Голосовое управление JARVIS на стройплощадке через AR-очки

### Технические улучшения

13. **Streaming responses**: Стриминг ответов агентов в Telegram в реальном времени
14. **Caching layer**: Redis для кешинования частых запросов к НТД
15. **Rate limiting**: Защита от перерасхода токенов Claude (ccusage интеграция)
16. **Observability**: OpenTelemetry для трейсинга запросов через всю цепочку
17. **A/B testing промптов**: Автоматическое сравнение эффективности промптов агентов
18. **Fine-tuning**: При накоплении данных — дообучение модели на инженерных задачах

---

## Метрики успеха

| Метрика | Цель (3 мес.) | Цель (6 мес.) |
|---------|--------------|--------------|
| Время обработки запроса | < 30 сек | < 15 сек |
| Точность классификации | > 85% | > 95% |
| Активных агентов | 4 | 8 |
| Записей в памяти | 500+ | 2000+ |
| Автоматизированных задач/день | 5 | 20 |
| Экономия времени | 2 часа/день | 5 часов/день |

---

*Документ создан: 10 апреля 2026*
*Версия: 1.0*
*Автор: JARVIS Architect (Claude) для Кайрата*
