#!/usr/bin/env bash
# Устанавливает на VPS ежедневный cron, который генерирует отчёт по логам
# и опционально отправляет его на work@baikulov-k-i.kz через msmtp.
#
# Запуск один раз:
#   export HOME=/c/tmp/sshhome
#   bash scripts/setup_agsk3_stats_cron.sh
#
# После установки:
#   - Отчёты лежат в /opt/agsk3/stats/daily-YYYY-MM-DD.txt (хранятся 30 дней)
#   - Запускается ежедневно в 08:00 по Астане (03:00 UTC)
#   - Если на сервере настроен msmtp — отчёт уходит на work@baikulov-k-i.kz
#   - Чтобы настроить email, см. инструкцию в конце вывода скрипта

set -euo pipefail

VPS="root@185.129.49.42"
EMAIL_TO="work@baikulov-k-i.kz"

payload=$(cat <<REMOTE
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# 1. Установить msmtp, если его нет (для опционального email)
if ! command -v msmtp >/dev/null 2>&1; then
  apt-get update -q </dev/null
  apt-get install -y -q -o Dpkg::Options::="--force-confold" msmtp msmtp-mta ca-certificates </dev/null
fi

# 2. Создать директорию для отчётов
install -d -m 0755 /opt/agsk3/stats

# 3. Положить daily.sh — генератор отчёта
cat > /opt/agsk3/stats/daily.sh <<'DAILY'
#!/usr/bin/env bash
# Генерирует ежедневный отчёт по nginx-логам и опционально шлёт email.
set -euo pipefail
export LC_ALL=C  # nginx пишет месяцы по-английски — форсируем date на английский

DATE_ISO=\$(date -d "yesterday" +%Y-%m-%d)
DATE_NGINX=\$(date -d "yesterday" +%d/%b/%Y)
OUT="/opt/agsk3/stats/daily-\${DATE_ISO}.txt"
EMAIL_TO="__EMAIL__"

BOT_RE='bot|crawl|spider|curl|wget|python|scrapy|go-http|http-client|postman|facebook|ahrefs|semrush|pingdom|uptime|yandex|googlebot|bingbot|duckduck|slurp|archive[.]org|scanner|nmap|masscan'

LOG_CAT() { for f in /var/log/nginx/access.log*; do case "\$f" in *.gz) zcat "\$f";; *) cat "\$f";; esac; done; }
HUMAN() { awk -F'"' -v re="\$BOT_RE" 'tolower(\$6) !~ re && \$6 != ""'; }
BOTS()  { awk -F'"' -v re="\$BOT_RE" 'tolower(\$6) ~ re || \$6 == ""'; }

TMP=\$(mktemp)
LOG_CAT | grep -F "\$DATE_NGINX" > "\$TMP" || true

{
  echo "AGSK-3 — отчёт за \$DATE_ISO"
  echo "================================"
  echo
  echo "=== Всего ==="
  awk '{a[\$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}' "\$TMP"
  echo
  echo "=== Люди ==="
  HUMAN < "\$TMP" | awk '{a[\$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
  echo
  echo "=== Боты ==="
  BOTS < "\$TMP" | awk '{a[\$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
  echo
  echo "=== Топ-15 IP (люди) ==="
  HUMAN < "\$TMP" | awk '{print \$1}' | sort | uniq -c | sort -rn | head -15
  echo
  echo "=== Топ-15 URL (люди) ==="
  HUMAN < "\$TMP" | awk '{print \$7}' | sort | uniq -c | sort -rn | head -15
  echo
  echo "=== Топ-10 User-Agent (люди) ==="
  HUMAN < "\$TMP" | awk -F'"' '{print \$6}' | sort | uniq -c | sort -rn | head -10
  echo
  echo "=== Боты: топ-10 IP ==="
  BOTS < "\$TMP" | awk '{print \$1}' | sort | uniq -c | sort -rn | head -10
  echo
  echo "=== Коды ответов ==="
  awk -F'"' '{print \$3}' "\$TMP" | awk '{print \$2}' | sort | uniq -c | sort -rn | head -10
} > "\$OUT"

rm -f "\$TMP"

# Удаляем отчёты старше 30 дней
find /opt/agsk3/stats -name 'daily-*.txt' -mtime +30 -delete 2>/dev/null || true

# Если настроен msmtp с паролем — отправляем email
if [[ -f /etc/msmtprc && -n "\$EMAIL_TO" ]]; then
  if grep -q '^password' /etc/msmtprc 2>/dev/null; then
    {
      echo "From: AGSK-3 Stats <agsk3-stats@baikulov-k-i.kz>"
      echo "To: \$EMAIL_TO"
      echo "Subject: AGSK-3 stats \$DATE_ISO"
      echo "Content-Type: text/plain; charset=UTF-8"
      echo
      cat "\$OUT"
    } | msmtp -t 2>>/var/log/agsk3-stats-mail.log || true
  fi
fi
DAILY

# Подставляем адрес получателя
sed -i "s|__EMAIL__|${EMAIL_TO}|" /opt/agsk3/stats/daily.sh
chmod +x /opt/agsk3/stats/daily.sh

# 4. Cron в /etc/cron.d — 08:00 Астана (UTC+5) = 03:00 UTC
cat > /etc/cron.d/agsk3-stats <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * root /opt/agsk3/stats/daily.sh >> /var/log/agsk3-stats.log 2>&1
CRON

chmod 0644 /etc/cron.d/agsk3-stats

# 5. Шаблон msmtp-конфига (без пароля — юзер вставит сам)
if [[ ! -f /etc/msmtprc ]]; then
  cat > /etc/msmtprc <<'MSMTP'
# Gmail SMTP relay. Заполни 'password' своим App Password
# (создать: https://myaccount.google.com/apppasswords).
defaults
auth            on
tls             on
tls_trust_file  /etc/ssl/certs/ca-certificates.crt
logfile         /var/log/msmtp.log

account         gmail
host            smtp.gmail.com
port            587
from            baikulovk6779@gmail.com
user            baikulovk6779@gmail.com
# password        <ВСТАВЬ_16-значный_App_Password_здесь>

account default : gmail
MSMTP
  chmod 0600 /etc/msmtprc
fi

# 6. Прогон для теста (сгенерирует отчёт за вчера)
if /opt/agsk3/stats/daily.sh 2>&1; then
  echo ">>> Тестовый прогон OK"
else
  echo ">>> Тестовый прогон упал — смотри вывод выше"
fi

echo
echo ">>> Установлено:"
echo "   /opt/agsk3/stats/daily.sh         — генератор отчёта"
echo "   /etc/cron.d/agsk3-stats           — cron (03:00 UTC = 08:00 Астана)"
echo "   /etc/msmtprc                      — шаблон SMTP (дополни password)"
echo "   /opt/agsk3/stats/daily-*.txt      — сами отчёты (30 дней)"
echo "   /var/log/agsk3-stats.log          — лог cron"
echo "   /var/log/agsk3-stats-mail.log     — лог отправки писем"
REMOTE
)

echo ">>> Устанавливаю на \$VPS ..."
ssh -o ConnectTimeout=10 "$VPS" "bash -s" <<<"$payload"

cat <<'HELP'

=== Готово! ===

Cron работает СРАЗУ — отчёты начнут копиться в /opt/agsk3/stats/.
Посмотреть свежий:
  ssh root@185.129.49.42 "cat /opt/agsk3/stats/daily-$(date -d yesterday +%Y-%m-%d).txt"

ЧТОБЫ ВКЛЮЧИТЬ EMAIL на work@baikulov-k-i.kz:
1. Создай Gmail App Password:
   https://myaccount.google.com/apppasswords
   (нужен 2FA, выбрать "Mail", получить 16-значный код, например: abcd efgh ijkl mnop)

2. Впиши его на сервере (одна команда, вставь свой код вместо ХХХХ):
   ssh root@185.129.49.42 'sed -i "s|# password.*|password        XXXX XXXX XXXX XXXX|" /etc/msmtprc'

3. Проверить отправку:
   ssh root@185.129.49.42 '/opt/agsk3/stats/daily.sh && tail /var/log/agsk3-stats-mail.log'

Если в почте не пришло — проверь /var/log/msmtp.log на VPS.

HELP
