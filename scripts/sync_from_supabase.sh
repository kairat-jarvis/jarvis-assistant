#!/bin/bash
# Автоматическая синхронизация Supabase → локальный PostgreSQL (jarvis_local)
# Запускается кроном каждые 15 минут

DIR="/Users/kairat/Claude Code/JARVIS ASSISTANT"
LOG="$DIR/logs/sync_supabase.log"
PYTHON="$DIR/.venv/bin/python"

mkdir -p "$DIR/logs"

# Загружаем переменные окружения
set -a
source "$DIR/.env"
set +a

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск sync Supabase → local" >> "$LOG"

"$PYTHON" "$DIR/scripts/migrate_jarvis_from_supabase.py" --from-supabase >> "$LOG" 2>&1
EXIT=$?

if [ $EXIT -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ОШИБКА (exit=$EXIT)" >> "$LOG"
fi

# Ротация лога: оставляем последние 500 строк
tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
