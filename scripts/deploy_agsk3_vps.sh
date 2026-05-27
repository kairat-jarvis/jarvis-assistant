#!/usr/bin/env bash
# Разворачивает окружение для FastAPI-приложения AGSK-3 на свежем Ubuntu 22.04/24.04.
# Запускать НА VPS под root:
#   ssh root@185.129.49.42
#   curl -O https://... (или scp с локальной машины)
#   bash deploy_agsk3_vps.sh
#
# Идемпотентен — можно перезапускать. Код заливается отдельно через sync_agsk3_to_vps.sh.

set -euo pipefail

DOMAIN="agsk-3.baikulov-k-i.kz"
APP_USER="agsk3"
APP_DIR="/opt/agsk3"
VENV_DIR="${APP_DIR}/venv"
SERVICE_NAME="agsk3"
CERT_EMAIL="baikulovk6779@gmail.com"

log() { echo -e "\033[1;36m>>> $*\033[0m"; }

# ─── 1. Проверки ──────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "Запускать под root (или через sudo)." >&2
  exit 1
fi

# ─── 2. Системные пакеты ──────────────────────────────────────────────────────
log "Обновление apt и установка пакетов"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  nginx \
  certbot python3-certbot-nginx \
  ufw \
  curl ca-certificates \
  git

# ─── 3. Пользователь приложения ───────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
  log "Создаю системного пользователя $APP_USER"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$APP_DIR"

# ─── 4. Python venv + зависимости ─────────────────────────────────────────────
log "Создаю venv и ставлю зависимости"
if [[ ! -d "$VENV_DIR" ]]; then
  sudo -u "$APP_USER" python3 -m venv "$VENV_DIR"
fi

# requirements.txt должен уже быть залит в $APP_DIR (sync-скриптом).
if [[ -f "$APP_DIR/requirements.txt" ]]; then
  sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip wheel
  sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
  # gunicorn в requirements нет, но удобен для graceful-reload; uvicorn и так умеет.
else
  echo "!!! $APP_DIR/requirements.txt не найден. Сначала запусти sync_agsk3_to_vps.sh с локальной машины."
  echo "    Продолжаю настройку без установки зависимостей — повтори шаг pip install после sync."
fi

# ─── 5. .env (Supabase креды) ─────────────────────────────────────────────────
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  log "Создаю шаблон .env (заполни SUPABASE_KEY реальным значением!)"
  cat > "$ENV_FILE" <<'EOF'
SUPABASE_URL=https://omykcphkzmmqpwswwfsw.supabase.co
SUPABASE_KEY=__ЗАМЕНИТЬ_НА_РЕАЛЬНЫЙ_ANON_KEY__
EOF
  chown "$APP_USER:$APP_USER" "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
fi

# ─── 6. systemd unit для uvicorn ──────────────────────────────────────────────
log "Создаю systemd unit $SERVICE_NAME.service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=AGSK-3 FastAPI (uvicorn)
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${APP_DIR}
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
# Стартуем только если есть app.py (иначе упадёт, надо сначала залить код)
if [[ -f "$APP_DIR/app.py" ]]; then
  systemctl restart "$SERVICE_NAME"
  sleep 2
  systemctl is-active --quiet "$SERVICE_NAME" \
    && log "uvicorn запущен" \
    || { echo "!!! uvicorn не стартовал. Логи: journalctl -u $SERVICE_NAME -n 50"; journalctl -u "$SERVICE_NAME" -n 30 --no-pager; }
else
  log "app.py ещё не залит — сервис настроен, но не запущен. Запустишь после sync."
fi

# ─── 7. nginx reverse proxy ───────────────────────────────────────────────────
log "Настраиваю nginx для $DOMAIN"
NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}"
cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }
}
EOF

ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/${DOMAIN}"
# Снять дефолтный vhost
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

# ─── 8. Let's Encrypt SSL ─────────────────────────────────────────────────────
log "Получаю SSL-сертификат для $DOMAIN"
echo "ВНИМАНИЕ: убедись, что A-запись $DOMAIN → $(curl -s ifconfig.me) уже прописана в DNS (Plesk)."
read -rp "DNS прописан и распространился? (y/N) " ok
if [[ "${ok,,}" == "y" ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL" --redirect || \
    echo "!!! certbot не получил сертификат — проверь DNS и запусти вручную: certbot --nginx -d $DOMAIN"
else
  log "Пропускаю certbot. Запустишь вручную: certbot --nginx -d $DOMAIN -m $CERT_EMAIL --agree-tos --redirect"
fi

# ─── 9. UFW firewall ──────────────────────────────────────────────────────────
log "Настраиваю UFW firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp        comment 'SSH'
ufw allow 80/tcp        comment 'HTTP'
ufw allow 443/tcp       comment 'HTTPS'
ufw --force enable

# ─── 10. Итог ─────────────────────────────────────────────────────────────────
log "Готово."
echo "──────────────────────────────────────────────────────────"
echo "  Домен:         https://${DOMAIN}"
echo "  Код:           ${APP_DIR}"
echo "  Сервис:        systemctl status ${SERVICE_NAME}"
echo "  Логи uvicorn:  journalctl -u ${SERVICE_NAME} -f"
echo "  Логи nginx:    tail -f /var/log/nginx/access.log /var/log/nginx/error.log"
echo "  Перезапуск:    systemctl restart ${SERVICE_NAME}"
echo "──────────────────────────────────────────────────────────"
echo "Дальше:"
echo "  1. Проверь .env: cat $ENV_FILE (подставь реальный SUPABASE_KEY если не был залит)"
echo "  2. Залей код: с локальной машины 'bash scripts/sync_agsk3_to_vps.sh'"
echo "  3. Проверь: curl -I https://${DOMAIN}/"
