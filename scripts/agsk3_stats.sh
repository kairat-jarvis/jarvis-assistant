#!/usr/bin/env bash
# Статистика посещений AGSK-3 из nginx access logs на VPS.
# Один SSH-вход на запуск — пароль вводите один раз.
#
# Запуск (из Git Bash, HOME=/c/tmp/sshhome):
#   bash scripts/agsk3_stats.sh                  — сводка (люди/боты, 7 дней, топ-10 IP с geo)
#   bash scripts/agsk3_stats.sh today            — сегодня детально (люди + боты + топ URL)
#   bash scripts/agsk3_stats.sh day 2026-04-22   — конкретная дата
#   bash scripts/agsk3_stats.sh week             — 7 дней по дням
#   bash scripts/agsk3_stats.sh top-ips [N]      — топ IP с geo (N=20)
#   bash scripts/agsk3_stats.sh top-paths [N]    — топ URL (только люди)
#   bash scripts/agsk3_stats.sh bots             — активность ботов отдельно
#   bash scripts/agsk3_stats.sh ip 1.2.3.4       — все запросы от IP + geo
#   bash scripts/agsk3_stats.sh raw              — хвост сырого лога
#
# Бот-фильтр: User-Agent содержит bot|crawl|spider|curl|wget|python|scrapy|
#   Go-http|http-client|postman|facebook|ahrefs|semrush|pingdom|uptime
# Geo: ip-api.com (бесплатно, 45 req/min, без ключа) — вызывается локально.
#
# «Уникальные IP» ≠ люди: ЕШДИ/корпоративный NAT показывает один внешний IP
# на всё ведомство. Реальных пользователей всегда больше.

set -euo pipefail

VPS="root@185.129.49.42"
cmd="${1:-summary}"
arg="${2:-}"

# Регэксп ботов для awk (case-insensitive via tolower)
BOT_RE='bot|crawl|spider|curl|wget|python|scrapy|go-http|http-client|postman|facebook|ahrefs|semrush|pingdom|uptime|yandex|googlebot|bingbot|duckduck|slurp|archive[.]org|scanner|nmap|masscan'

# Шлём bash-payload по ssh одной командой.
# $1 nginx combined: IP - user [time] "req" status bytes "ref" "UA"
# FS='"' → $1=prefix, $2=req, $3=mid, $4=ref, $5=mid, $6=UA
# Сначала фильтруем по дате (через grep), потом awk парсит.

build_payload() {
  cat <<REMOTE_HEAD
LOG_CAT() { for f in /var/log/nginx/access.log*; do case "\$f" in *.gz) zcat "\$f";; *) cat "\$f";; esac; done; }
BOT_RE='$BOT_RE'
# HUMAN: печатает только строки, где UA НЕ матчит бот-регэксп и не пустой
HUMAN() { awk -F'"' -v re="\$BOT_RE" 'tolower(\$6) !~ re && \$6 != ""'; }
BOTS()  { awk -F'"' -v re="\$BOT_RE" 'tolower(\$6) ~ re || \$6 == ""'; }
REMOTE_HEAD

  case "$cmd" in
    today)
      cat <<'REMOTE'
D=$(date +%d/%b/%Y)
echo "=== Сегодня ($D) ==="
LOG_CAT | grep -F "$D" > /tmp/_today_$$
echo "--- Всего ---"
awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}' /tmp/_today_$$
echo "--- Люди ---"
HUMAN < /tmp/_today_$$ | awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
echo "--- Боты ---"
BOTS  < /tmp/_today_$$ | awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
echo "--- Топ IP (люди) ---"
HUMAN < /tmp/_today_$$ | awk '{print $1}' | sort | uniq -c | sort -rn | head -10
echo "--- Топ URL (люди) ---"
HUMAN < /tmp/_today_$$ | awk '{print $7}' | sort | uniq -c | sort -rn | head -10
rm -f /tmp/_today_$$
REMOTE
      ;;

    day)
      [[ -z "$arg" ]] && { echo "Укажи дату: bash $0 day 2026-04-22" >&2; exit 1; }
      d=$(date -d "$arg" +%d/%b/%Y 2>/dev/null) || { echo "Неверная дата: $arg" >&2; exit 1; }
      printf 'D=%q\n' "$d"
      cat <<'REMOTE'
echo "=== $D ==="
LOG_CAT | grep -F "$D" > /tmp/_day_$$
echo "--- Всего ---"
awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}' /tmp/_day_$$
echo "--- Люди ---"
HUMAN < /tmp/_day_$$ | awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
echo "--- Боты ---"
BOTS  < /tmp/_day_$$ | awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
echo "--- Топ IP (люди) ---"
HUMAN < /tmp/_day_$$ | awk '{print $1}' | sort | uniq -c | sort -rn | head -10
echo "--- Топ URL (люди) ---"
HUMAN < /tmp/_day_$$ | awk '{print $7}' | sort | uniq -c | sort -rn | head -10
rm -f /tmp/_day_$$
REMOTE
      ;;

    week)
      echo 'echo "=== Последние 7 дней (люди / боты) ==="'
      printf 'printf "%%-12s %%10s %%10s %%8s %%8s\\n" "Дата" "Люди-IP" "Люди-req" "Бот-IP" "Бот-req"\n'
      for i in 6 5 4 3 2 1 0; do
        d=$(date -d "-$i day" +%d/%b/%Y)
        iso=$(date -d "-$i day" +%Y-%m-%d)
        cat <<REMOTE
LOG_CAT | grep -F $(printf '%q' "$d") > /tmp/_w_\$\$
H_IP=\$(HUMAN < /tmp/_w_\$\$ | awk '{a[\$1]=1} END {print length(a)+0}')
H_RQ=\$(HUMAN < /tmp/_w_\$\$ | wc -l)
B_IP=\$(BOTS  < /tmp/_w_\$\$ | awk '{a[\$1]=1} END {print length(a)+0}')
B_RQ=\$(BOTS  < /tmp/_w_\$\$ | wc -l)
printf "%-12s %10d %10d %8d %8d\n" "$iso" "\$H_IP" "\$H_RQ" "\$B_IP" "\$B_RQ"
rm -f /tmp/_w_\$\$
REMOTE
      done
      ;;

    top-ips)
      n="${arg:-20}"
      printf 'echo "=== Топ %s IP за всё время (только люди) ==="\n' "$n"
      printf 'HUMAN < <(LOG_CAT) | awk "{print \\$1}" | sort | uniq -c | sort -rn | head -%s\n' "$n"
      ;;

    top-paths)
      n="${arg:-20}"
      printf 'echo "=== Топ %s URL (только люди) ==="\n' "$n"
      printf 'HUMAN < <(LOG_CAT) | awk "{print \\$7}" | sort | uniq -c | sort -rn | head -%s\n' "$n"
      ;;

    bots)
      cat <<'REMOTE'
echo "=== Активность ботов (все логи) ==="
LOG_CAT > /tmp/_all_$$
echo "--- Всего по ботам ---"
BOTS < /tmp/_all_$$ | awk '{a[$1]=1; n++} END {printf "Уникальных IP: %d\nЗапросов:      %d\n", length(a), n+0}'
echo "--- Топ-15 бот-IP ---"
BOTS < /tmp/_all_$$ | awk '{print $1}' | sort | uniq -c | sort -rn | head -15
echo "--- Топ-15 User-Agent ---"
BOTS < /tmp/_all_$$ | awk -F'"' '{print $6}' | sort | uniq -c | sort -rn | head -15
rm -f /tmp/_all_$$
REMOTE
      ;;

    ip)
      [[ -z "$arg" ]] && { echo "Укажи IP: bash $0 ip 1.2.3.4" >&2; exit 1; }
      printf 'echo "=== Запросы от %s (последние 50) ==="\n' "$arg"
      printf 'LOG_CAT | grep -F %q | awk -F'\''"'\'' '\''{split($1,a," "); print a[4], a[5], a[6], $2, $6}'\'' | tail -50\n' "$arg "
      ;;

    raw)
      echo 'tail -50 /var/log/nginx/access.log'
      ;;

    summary|*)
      cat <<'REMOTE'
D=$(date +%d/%b/%Y)
echo "=== Сводка: сегодня ($D) ==="
LOG_CAT | grep -F "$D" > /tmp/_s_$$
printf "Всего: "; awk '{a[$1]=1; n++} END {printf "IP=%d, req=%d\n", length(a), n+0}' /tmp/_s_$$
printf "Люди: "; HUMAN < /tmp/_s_$$ | awk '{a[$1]=1; n++} END {printf "IP=%d, req=%d\n", length(a), n+0}'
printf "Боты: "; BOTS  < /tmp/_s_$$ | awk '{a[$1]=1; n++} END {printf "IP=%d, req=%d\n", length(a), n+0}'
rm -f /tmp/_s_$$
echo
echo "=== Последние 7 дней ==="
REMOTE
      printf 'printf "%%-12s %%10s %%10s %%8s %%8s\\n" "Дата" "Люди-IP" "Люди-req" "Бот-IP" "Бот-req"\n'
      for i in 6 5 4 3 2 1 0; do
        d=$(date -d "-$i day" +%d/%b/%Y)
        iso=$(date -d "-$i day" +%Y-%m-%d)
        cat <<REMOTE
LOG_CAT | grep -F $(printf '%q' "$d") > /tmp/_w_\$\$
H_IP=\$(HUMAN < /tmp/_w_\$\$ | awk '{a[\$1]=1} END {print length(a)+0}')
H_RQ=\$(HUMAN < /tmp/_w_\$\$ | wc -l)
B_IP=\$(BOTS  < /tmp/_w_\$\$ | awk '{a[\$1]=1} END {print length(a)+0}')
B_RQ=\$(BOTS  < /tmp/_w_\$\$ | wc -l)
printf "%-12s %10d %10d %8d %8d\n" "$iso" "\$H_IP" "\$H_RQ" "\$B_IP" "\$B_RQ"
rm -f /tmp/_w_\$\$
REMOTE
      done
      echo 'echo'
      echo 'echo "=== Топ-10 IP (люди) ==="'
      echo 'HUMAN < <(LOG_CAT) | awk "{print \$1}" | sort | uniq -c | sort -rn | head -10'
      ;;
  esac
}

# Запускаем ssh один раз с payload
payload=$(build_payload)
server_out=$(ssh -o ConnectTimeout=5 "$VPS" "bash -s" <<<"$payload")

# Geo-обогащение IP (если команда выводит IP в начале строк с префиксом "    N IP")
# Делаем локально — ip-api.com с батчем до 100 IP.
enrich_geo() {
  local input="$1"
  # Собираем уникальные IP из строк вида "   252 89.218.211.186"
  local ips
  ips=$(echo "$input" | grep -oE '^\s*[0-9]+\s+[0-9]{1,3}(\.[0-9]{1,3}){3}\b' | awk '{print $2}' | sort -u | head -100)
  if [[ -z "$ips" ]]; then
    echo "$input"
    return
  fi
  # Формируем JSON-массив для батча
  local json
  json=$(echo "$ips" | awk 'BEGIN{printf "["} NR>1{printf ","} {printf "\"%s\"", $1} END{printf "]"}')
  # Вызов ip-api.com батч-эндпоинта
  local geo
  geo=$(curl -s --max-time 8 -H 'Content-Type: application/json' -d "$json" \
        'http://ip-api.com/batch?fields=query,country,city,isp' 2>/dev/null || echo '[]')
  # Строим lookup table IP → "Country, City (ISP)"
  declare -A MAP
  while IFS=$'\t' read -r ip country city isp; do
    [[ -z "$ip" ]] && continue
    local label="${country:-?}"
    [[ -n "$city" ]] && label="$label, $city"
    [[ -n "$isp" ]] && label="$label [$isp]"
    MAP["$ip"]="$label"
  done < <(echo "$geo" | python3 -c '
import sys, json
try:
  for r in json.load(sys.stdin):
    print("\t".join([r.get("query",""), r.get("country",""), r.get("city",""), r.get("isp","")]))
except: pass
' 2>/dev/null)
  # Подменяем каждую строку IP-шку на "IP  ← geo"
  while IFS= read -r line; do
    local ip
    ip=$(echo "$line" | grep -oE '[0-9]{1,3}(\.[0-9]{1,3}){3}' | head -1)
    if [[ -n "$ip" && -n "${MAP[$ip]:-}" ]]; then
      printf "%s  ← %s\n" "$line" "${MAP[$ip]}"
    else
      echo "$line"
    fi
  done <<<"$input"
}

# Для top-ips, summary и ip — обогащаем geo. Для остальных — просто печатаем.
case "$cmd" in
  top-ips|summary|today|day|bots)
    enrich_geo "$server_out"
    ;;
  *)
    echo "$server_out"
    ;;
esac
