#!/usr/bin/env bash
# Синхронизирует локальный код AGSK-3 на VPS через scp (rsync в Git Bash на Windows нет).
# Запускать ЛОКАЛЬНО из Git Bash в g:\Мой диск\AI\Claude Code\JARVIS ASSISTANT\:
#   bash scripts/sync_agsk3_to_vps.sh
#
# Перед запуском — убедись, что можешь подключиться: ssh root@$VPS_HOST
# (публичный ключ добавлен или пароль под рукой).

set -euo pipefail

VPS_HOST="185.129.49.42"
VPS_USER="root"
REMOTE_DIR="/opt/agsk3"
SRC_DIR="/g/Мой диск/AI/Claude Code/InSmart AGSK-3"

# Файлы и папки проекта, которые НУЖНЫ на проде.
# ИСКЛЮЧАЕМ: .git, .vercel*, __pycache__, output/, catalog/ (100+ MB md), tools/agsk.db (54 MB SQLite),
#            .env (свой на сервере), CLAUDE.md (IDE-инструкции).
INCLUDE=(
  "app.py"
  "requirements.txt"
  "Procfile"
  "Logo.png"
  "public"
  "tools/create_stamp_ref.py"
  "tools/convert_agsk.py"
  "tools/migrate_to_supabase.py"
  "tools/load_april_catalog.py"
  "tools/templates"
)

log() { echo -e "\033[1;36m>>> $*\033[0m"; }

# ─── 0. Проверки ──────────────────────────────────────────────────────────────
if [[ ! -d "$SRC_DIR" ]]; then
  echo "Не нашёл исходники: $SRC_DIR" >&2
  exit 1
fi

# Тест SSH
log "Проверяю SSH до $VPS_USER@$VPS_HOST"
ssh -o BatchMode=no -o ConnectTimeout=5 "$VPS_USER@$VPS_HOST" "echo OK" || {
  echo "!!! SSH не подключается. Проверь, что ключ добавлен или готов ввести пароль."
  exit 1
}

# ─── 1. Готовлю временный tar-архив локально ──────────────────────────────────
TMP_TAR="$(mktemp -t agsk3_sync_XXXX.tar.gz)"
log "Упаковываю в $TMP_TAR"

# tar -C SRC_DIR <files>. Нужно запускать из SRC_DIR, чтобы пути были относительные.
pushd "$SRC_DIR" >/dev/null
tar -czf "$TMP_TAR" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  "${INCLUDE[@]}"
popd >/dev/null

size=$(du -h "$TMP_TAR" | cut -f1)
log "Архив готов: $size"

# ─── 2. Заливка на VPS ────────────────────────────────────────────────────────
log "Заливаю на VPS в /tmp/"
scp "$TMP_TAR" "$VPS_USER@$VPS_HOST:/tmp/agsk3_sync.tar.gz"

# ─── 3. Распаковка на сервере ─────────────────────────────────────────────────
log "Распаковываю в $REMOTE_DIR и выставляю права"
ssh "$VPS_USER@$VPS_HOST" bash -s <<EOF
set -euo pipefail
install -d -o agsk3 -g agsk3 -m 0755 "$REMOTE_DIR" 2>/dev/null || true
tar -xzf /tmp/agsk3_sync.tar.gz -C "$REMOTE_DIR"
chown -R agsk3:agsk3 "$REMOTE_DIR"
rm /tmp/agsk3_sync.tar.gz

# Если venv уже есть — доустанавливаем зависимости (на случай изменения requirements.txt)
if [[ -f "$REMOTE_DIR/venv/bin/pip" && -f "$REMOTE_DIR/requirements.txt" ]]; then
  sudo -u agsk3 "$REMOTE_DIR/venv/bin/pip" install -r "$REMOTE_DIR/requirements.txt"
fi

# Рестарт сервиса, если он уже настроен
if systemctl list-unit-files | grep -q '^agsk3\.service'; then
  systemctl restart agsk3
  sleep 2
  systemctl is-active --quiet agsk3 && echo ">>> agsk3 service OK" || {
    echo "!!! agsk3 service failed, last logs:"
    journalctl -u agsk3 -n 20 --no-pager
  }
fi
EOF

rm -f "$TMP_TAR"
log "Готово. Проверь: curl -I https://agsk-3.baikulov-k-i.kz/"
