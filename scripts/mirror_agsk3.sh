#!/usr/bin/env bash
# Зеркалирует сайт agsk-3.baikulov-k.com в load/agsk-3/
# для последующей заливки на хостинг РК (hoster.kz, Plesk -> httpdocs/).
#
# Использование:
#   bash scripts/mirror_agsk3.sh
#
# Требует: curl (wget не нужен).

set -euo pipefail

SRC="https://agsk-3.baikulov-k.com"
DEST="load/agsk-3"

mkdir -p "$DEST"

# Список ресурсов сайта (статический одностраничник).
# При добавлении новых файлов на прод — допиши сюда.
FILES=(
  "index.html"
  "logo.png"
)

echo ">>> Mirror $SRC -> $DEST"
for f in "${FILES[@]}"; do
  url="$SRC/$f"
  out="$DEST/$f"
  mkdir -p "$(dirname "$out")"
  http_code=$(curl -sSL -w "%{http_code}" -o "$out" "$url")
  size=$(wc -c < "$out" | tr -d ' ')
  if [[ "$http_code" == "200" ]]; then
    echo "  OK   $f  ($size bytes)"
  else
    echo "  FAIL $f  HTTP $http_code" >&2
    rm -f "$out"
  fi
done

echo ">>> Done. Upload contents of $DEST/ to Plesk httpdocs/ via FTP or File Manager."
