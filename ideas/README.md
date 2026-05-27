# 💡 Банк идей JARVIS

Идеи поступают из Telegram → n8n → GitHub API → эта папка.

## Формат файла
Каждая идея — отдельный `.md` файл:
```
ideas/YYYY-MM-DD_HH-MM_slug.md
```

## Фронтматтер
```yaml
---
date: YYYY-MM-DD HH:MM
source: telegram
status: new          # new | evaluating | planned | in_progress | done | dismissed
feasibility: ~       # 1-10, заполняет JARVIS
impact: ~            # 1-10, заполняет JARVIS
tags: []
---
```

## Статусы
- `new` — только что поступила
- `evaluating` — JARVIS оценивает
- `planned` — включена в план
- `in_progress` — в работе
- `done` — реализована
- `dismissed` — отклонена с причиной
