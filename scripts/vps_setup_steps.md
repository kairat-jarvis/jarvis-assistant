# Развёртывание AGSK-3 на VPS hoster.kz

- **VPS:** `185.129.49.42` (Астана, hoster.kz AS207333)
- **Hostname:** `vps.baikulov-k-i.kz`
- **Публичный сайт:** `https://agsk-3.baikulov-k-i.kz/`
- **ОС:** Ubuntu 24.04 LTS
- **Приложение:** FastAPI (`/opt/agsk3/app.py`) + uvicorn + nginx + Let's Encrypt
- **БД:** Supabase (внешний, не на этом VPS)

---

## Шаг 0. Добавить A-запись в Plesk (Эконом-1)

**Сделать ПЕРВЫМ делом** — нужно для Let's Encrypt.

1. Открой Plesk: https://pkz37.hoster.kz:8443/
2. Сайты и домены → `baikulov-k-i.kz` → **DNS-настройки**
3. **Добавить запись**:
   - **Тип:** A
   - **Имя (subdomain):** `agsk-3`
   - **IP-адрес:** `185.129.49.42`
   - **TTL:** 3600 (или по умолчанию)
4. Сохранить. Дождаться ~5–10 минут.

Проверка из Git Bash:
```bash
nslookup agsk-3.baikulov-k-i.kz 8.8.8.8
# Должен показать 185.129.49.42
```

---

## Шаг 1. Первое подключение к VPS

Из письма hoster.kz возьми root-пароль. В Git Bash:

```bash
ssh root@185.129.49.42
# При первом подключении — подтвердить fingerprint: yes
# Ввести пароль из письма
```

### (рекомендуется) Настроить SSH-ключ — без пароля

Если пока нет ключа локально:
```bash
# На локальной машине (Git Bash)
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "baikulovk6779@gmail.com"
# Enter, Enter, Enter (без парольной фразы — либо с ней, на твой выбор)

# Скопировать ключ на VPS
ssh-copy-id root@185.129.49.42
# Ввести root-пароль последний раз

# Проверка — должно пустить без пароля
ssh root@185.129.49.42 "echo OK"
```

---

## Шаг 2. Запустить deploy-скрипт на VPS

С локальной машины залей deploy-скрипт и выполни:

```bash
# Локально (Git Bash, из папки JARVIS ASSISTANT)
scp scripts/deploy_agsk3_vps.sh root@185.129.49.42:/root/

# Подключиться и запустить
ssh root@185.129.49.42
bash /root/deploy_agsk3_vps.sh
```

Скрипт:
- Ставит python3, pip, venv, nginx, certbot, ufw
- Создаёт системного пользователя `agsk3` и папку `/opt/agsk3/`
- Настраивает systemd-unit `agsk3.service` (uvicorn на `127.0.0.1:8000`)
- Настраивает nginx reverse proxy для `agsk-3.baikulov-k-i.kz`
- Запрашивает Let's Encrypt SSL (спросит «DNS прописан? y/N» — если шаг 0 сделан, отвечай `y`)
- Включает UFW (разрешает 22/80/443)

Если certbot ругается «unable to verify domain» — значит DNS ещё не распространился. Подожди 5–10 минут и запусти вручную:
```bash
certbot --nginx -d agsk-3.baikulov-k-i.kz -m baikulovk6779@gmail.com --agree-tos --redirect
```

---

## Шаг 3. Залить код AGSK-3 на VPS

С локальной машины:

```bash
bash scripts/sync_agsk3_to_vps.sh
```

Скрипт упакует нужные файлы (без `catalog/`, `output/`, `tools/agsk.db`, `__pycache__`, `.git`), зальёт tar.gz по scp, распакует на сервере в `/opt/agsk3/`, переставит права на пользователя `agsk3`, установит requirements и перезапустит сервис.

Сколько заливается: ~2–5 МБ (только код + шаблоны + public/). Каталог АГСК-3 на проде живёт в Supabase — локальные `.md`/`.db` не нужны.

---

## Шаг 4. Проверить .env с ключом Supabase

```bash
ssh root@185.129.49.42 "cat /opt/agsk3/.env"
```

Должно быть:
```
SUPABASE_URL=https://omykcphkzmmqpwswwfsw.supabase.co
SUPABASE_KEY=eyJhbGci...реальный_anon_key...
```

Если в `.env` стоит заглушка `__ЗАМЕНИТЬ...__` — подставь реальный ключ (возьми из `/Users/kairat/Claude Code/InSmart AGSK-3/app.py`, строка 28):

```bash
ssh root@185.129.49.42
nano /opt/agsk3/.env
# заменить SUPABASE_KEY= на реальный
systemctl restart agsk3
```

---

## Шаг 5. Проверка

### С локальной машины
```bash
curl -I https://agsk-3.baikulov-k-i.kz/
# Ожидается: HTTP/2 200, Server: nginx
```

### В браузере
Открой `https://agsk-3.baikulov-k-i.kz/` — должна появиться страница AGSK-3.

### Проверка ЕШДИ
- Прогон: https://checkip.sts.kz/ → ввести `agsk-3.baikulov-k-i.kz`
- С рабочего компа Госэкспертизы: `https://agsk-3.baikulov-k-i.kz/` должен открываться без блокировки ЕШДИ.

---

## Обслуживание

### Деплой изменений кода
После правок в `/Users/kairat/Claude Code/InSmart AGSK-3/`:
```bash
bash scripts/sync_agsk3_to_vps.sh
```
Скрипт сам рестартует сервис.

### Логи
```bash
ssh root@185.129.49.42
journalctl -u agsk3 -f          # live-логи uvicorn
tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Ручной рестарт
```bash
ssh root@185.129.49.42 "systemctl restart agsk3 && systemctl status agsk3"
```

### Обновление SSL
Certbot сам продлевает (таймер `certbot.timer`). Проверка:
```bash
systemctl list-timers | grep certbot
certbot renew --dry-run
```

---

## Откат / отключение

### Временно остановить сервис
```bash
ssh root@185.129.49.42 "systemctl stop agsk3"
```

### Полностью удалить (если надо пересоздать VPS)
В hoster.kz кабинете: Облако → Облачные серверы → VDS → **Удалить**. VPS погашен, платёж больше не списывается.

---

## Устранение проблем

| Симптом | Диагностика | Решение |
|---------|-------------|---------|
| `502 Bad Gateway` | uvicorn не запущен | `journalctl -u agsk3 -n 50` → чаще всего проблема с `.env` или нехватка зависимостей |
| `certbot: Challenge failed` | DNS не распространился | Подождать 10 мин, `dig agsk-3.baikulov-k-i.kz` должен вернуть `185.129.49.42` |
| `504 Gateway Timeout` | uvicorn висит на долгом запросе | В `/etc/nginx/sites-available/agsk-3.baikulov-k-i.kz` уже `proxy_read_timeout 300`; если мало — увеличить |
| ЕШДИ всё равно блокирует | checkip показывает «не подключен» | Подождать сутки на синхронизацию ГТС, либо прописать MIC-notice в ps.kz (редкое требование) |
