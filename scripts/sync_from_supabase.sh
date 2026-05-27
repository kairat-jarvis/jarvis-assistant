#!/bin/bash
# Синхронизация JARVIS: Supabase → local PostgreSQL + git pull (ideas из GitHub)
# Запускается кроном каждые 15 минут

DIR="/Users/kairat/Claude Code/JARVIS ASSISTANT"
LOG="$DIR/logs/sync_supabase.log"
PYTHON="$DIR/.venv/bin/python"

mkdir -p "$DIR/logs"

# Загружаем переменные окружения
set -a
source "$DIR/.env"
set +a

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск sync" >> "$LOG"

# 1. Supabase → local PostgreSQL
"$PYTHON" "$DIR/scripts/migrate_jarvis_from_supabase.py" --from-supabase >> "$LOG" 2>&1
EXIT_SB=$?

if [ $EXIT_SB -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Supabase OK" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Supabase ОШИБКА (exit=$EXIT_SB)" >> "$LOG"
fi

# 2. GitHub → local (получаем новые идеи из ideas/)
cd "$DIR" && git pull --ff-only origin main >> "$LOG" 2>&1
EXIT_GIT=$?

if [ $EXIT_GIT -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] git pull OK" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] git pull ОШИБКА (exit=$EXIT_GIT)" >> "$LOG"
fi

# Ротация лога: оставляем последние 500 строк
tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
