# Design: JARVIS Pilot — Video Production Pipeline (Hyperframes)

**Date:** 2026-04-25
**Author:** Kairat Baikulov
**Status:** Approved

---

## Goal

Build a repeatable video production pipeline for the "Пилот JARVIS" course using Claude Code + Hyperframes. Each lesson: raw footage → cleaned MP4 → animated lecture video with pip cam + motion graphics.

---

## Project Location

```
/Users/kairat/Claude Code/Hyperframes\
```

Base: clone of [nateherkai/hyperframes-student-kit](https://github.com/nateherkai/hyperframes-student-kit)

---

## Approach

**Template-first (Approach B).** Build one master brand template for JARVIS Pilot, then run each lesson through the same pipeline. Quality and speed improve with each iteration as Claude Code accumulates skill knowledge.

---

## Project Structure

```
/Users/kairat/Claude Code/Hyperframes\
├── CLAUDE.md                          ← workspace guide (from student kit)
├── MOTION_PHILOSOPHY.md               ← aesthetic rules (from student kit)
├── DESIGN.jarvis-pilot.md             ← brand spec for this course
├── package.json
├── .env.example
├── .claude/
│   └── skills/
│       ├── make-a-video.md            ← from student kit
│       ├── hyperframes.md             ← from student kit
│       ├── gsap.md                    ← from student kit
│       ├── hyperframes-registry.md    ← from student kit
│       └── make-jarvis-lesson.md      ← custom: JARVIS Pilot specific
├── assets/
│   └── jarvis-pilot/
│       ├── colors.json
│       ├── logo.png
│       └── typography.json
└── video-projects/
    ├── jarvis-pilot-template/         ← master brand template
    ├── jarvis-pilot-L1/               ← Уровень 1
    ├── jarvis-pilot-L2/               ← Уровень 2
    └── jarvis-pilot-L3/               ← Уровень 3
```

Footage и `.docx` материалы курса остаются в `/Users/kairat/Claude Code/++Пилот JARVIS/`. Claude Code читает их оттуда.

---

## Brand Spec

| Property | Value |
|---|---|
| Background | `#0D0D0D` (near-black) |
| Accent | `#4A90E2` (blue) |
| Secondary | `#FFFFFF` |
| Font | Roboto Mono |
| Language | Russian |
| Format | 1920×1080, 60fps |

---

## Pip Layout

```
┌─────────────────────────────────────────┐
│  JARVIS Pilot · Уровень N  [progress]   │  title bar (48px)
│                                         │
│                                         │
│   ГЛАВНАЯ ЗОНА                          │
│   (анимации, схемы, терминал, текст)    │
│                                         │
│                           ┌──────────┐  │
│                           │  [cam]   │  │  pip: bottom-right, 25% width
│                           └──────────┘  │
│  ▶ Ключевой термин                      │  callout strip (32px)
└─────────────────────────────────────────┘
```

---

## Scene Types

| Сцена | Описание | Когда |
|---|---|---|
| **Title** | Анимированный заголовок урока, полный экран, 3–5 сек | Открывашка |
| **Explain** | Pip + схема или список слева | Объяснение концепции |
| **Terminal** | Pip + анимированный терминал (Claude команды) | Демо инструмента |
| **Callout** | Крупный текст по центру, акцентный цвет | Ключевая мысль |
| **Summary** | Список итогов с появлением пунктов | Конец урока |

---

## Custom Skill: `make-jarvis-lesson`

Поверх student kit skills, знает специфику курса:

- Бренд: `#4A90E2`, тёмный фон, Roboto Mono, pip bottom-right
- Язык: русский (транскрипция + тексты motion graphics)
- Структура уроков из `.docx` файлов курса
- Типовые сцены (Title / Explain / Terminal / Callout / Summary)
- Двухэтапные gates: preview → draft → final

---

## Per-Lesson Workflow

```
1. ПОДГОТОВКА FOOTAGE
   Источник: /Users/kairat/Claude Code/++Пилот JARVIS/<raw_файл>.mp4
   → вручную вырезать ретейки (любой редактор)
   → ffmpeg re-encode → video-projects/jarvis-pilot-LN/assets/clean.mp4

2. ЗАПУСК PIPELINE
   /make-jarvis-lesson video-projects/jarvis-pilot-LN/assets/clean.mp4
   → Claude читает /Users/kairat/Claude Code/++Пилот JARVIS/JARVIS_Pilot_LN_v2.docx
   → Whisper транскрибирует через OpenAI API (OPENAI_API_KEY в .env)
     → video-projects/jarvis-pilot-LN/assets/transcript.json
   → Claude планирует сцены по тайм-кодам
   → одобрить план

3. PREVIEW GATE 1
   npx hyperframes preview (localhost:3002)
   → голосовой фидбэк по тайм-кодам
   → Claude правит HTML live

4. DRAFT RENDER
   npx hyperframes render --quality draft
   → Claude проверяет ключевые кадры
   → финальный фидбэк

5. FINAL RENDER
   npx hyperframes render --quality standard --output renders/LN_final.mp4
```

**Ожидаемое время на урок:** 3–5 итераций, 30–60 мин.

---

## Setup Steps

1. `git clone https://github.com/nateherkai/hyperframes-student-kit` в `/Users/kairat/Claude Code/Hyperframes\`
2. `npm install`
3. Проверить: Node 20+, FFmpeg, Chrome (`npx hyperframes doctor`)
3a. Добавить `OPENAI_API_KEY` в `.env` (для Whisper транскрипции)
4. Добавить бренд-ассеты в `assets/jarvis-pilot/`
5. Создать `DESIGN.jarvis-pilot.md` с brand spec
6. Написать `.claude/skills/make-jarvis-lesson.md`
7. Создать `video-projects/jarvis-pilot-template/` — мастер-шаблон
8. Прогнать первый урок через полный pipeline

---

## Out of Scope

- Запись footage (остаётся за пользователем)
- Монтаж raw footage (вручную до pipeline)
- Shorts / вертикальный формат (только 16:9 лекции)
- Озвучка / TTS (живая запись голоса)
