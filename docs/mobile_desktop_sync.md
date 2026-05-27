# JARVIS: Синхронизация мобильный ↔ desktop

## Контекст

Рабочий workflow: VS Code (desktop) + мобильный Claude Code (claude.ai Project).
Цель — передавать идеи и мысли с мобильного, и чтобы JARVIS на desktop их знал.

## Архитектура

```
📱 Mobile (claude.ai Project)      🖥️ Desktop (VS Code + Claude Code CLI)
"идея: субагент MCP + AutoCAD"
        │
        ▼
  Supabase jarvis_memory  ──────────────────►  JARVIS читает из той же БД
  content_type: 'idea'                          (или через local sync)
  feasibility + impact
```

Идеи и мысли идут напрямую в Supabase — **без git push**.

## Что уже настроено

`JARVIS_SYSTEM_PROMPT.md` содержит правило для типа 💡 IDEA:
1. Классифицировать сообщение как идею
2. Оценить feasibility + impact (1–10)
3. Сохранить в `jarvis_memory` (Supabase) с тегами
4. Подтвердить сохранение одной строкой

## Когда нужен git push, а когда нет

| Действие | Git push нужен? |
|---|---|
| Написал идею на мобильном | ❌ Нет |
| Надиктовал заметку | ❌ Нет |
| Поставил задачу JARVIS | ❌ Нет |
| Изменил код / файлы проекта | ✅ Да |
| Обновил JARVIS_SYSTEM_PROMPT.md | ✅ Да |

## Условия для работы

**Мобильный (claude.ai Project):**
- Подключён Supabase MCP (проект `omykcphkzmmqpwswwfsw`)
- Загружен `JARVIS_SYSTEM_PROMPT.md` как системный промпт проекта

**Desktop (Claude Code CLI):**
- Читает из Supabase напрямую ИЛИ
- Запускает синхронизацию в локальный PostgreSQL:
  ```bash
  python scripts/migrate_jarvis_from_supabase.py --from-supabase
  ```

## Вывод

Git — только для кода. Память (идеи, заметки, задачи) — это база данных Supabase.
Мобильный и desktop используют одну и ту же БД → синхронизация мгновенная, без git.
