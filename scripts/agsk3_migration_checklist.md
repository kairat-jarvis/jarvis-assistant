# Миграция AGSK-3 на baikulov-k-i.kz (hoster.kz)

**Цель:** перенести `agsk-3.baikulov-k.com` (Vercel / AWS US, IP `216.198.79.65`) на домен `baikulov-k-i.kz` с хостингом в РК, чтобы ресурс проходил через ЕШДИ (ППРК №832).

**Состав сайта (подтверждён зеркалом):** `index.html` (35 KB) + `logo.png` (139 KB). Внешние зависимости: Google Fonts, YouTube iframe — подгружаются браузером, не требуют размещения.

---

## Шаг 1. Купить хостинг в РК

- Кабинет: https://hoster.kz/cabinet/
- Тариф: **«Виртуальный хостинг»** → самый младший (Plesk, SSD, ~1500 ₸/мес)
- Либо альтернативы с российской пропиской в РК: `ps.kz`, `activecloud.kz`
- После оплаты в письме придут: IP сервера, логин Plesk, FTP-доступ

## Шаг 2. Привязать домен в Plesk

1. Войти в Plesk (ссылка из письма).
2. **Websites & Domains** → **Add Domain** → `baikulov-k-i.kz`.
3. Document root оставить по умолчанию: `/var/www/vhosts/.../httpdocs/`.
4. Включить галочку **Secure the domain with Let's Encrypt** (бесплатный SSL).

## Шаг 3. Обновить DNS у регистратора

В кабинете **hoster.kz → Управление доменом** `baikulov-k-i.kz`:

- Если хостинг там же: выставить NS-серверы `ns1.hoster.kz` / `ns2.hoster.kz` / `ns3.hoster.kz` — всё настроится автоматически.
- Если хостинг у другого провайдера: создать **A-запись**

  | Name | Type | Value |
  |------|------|-------|
  | `@`  | A    | `<IP сервера из письма>` |
  | `www`| A    | `<IP сервера из письма>` |

- Распространение: 1–2 часа максимум.

## Шаг 4. Залить файлы сайта

Исходники лежат в `load/agsk-3/` (скачано скриптом `scripts/mirror_agsk3.sh`).

**Вариант A — Plesk File Manager (проще):**
1. Websites & Domains → `baikulov-k-i.kz` → **File Manager**.
2. Перейти в `httpdocs/`, удалить дефолтный `index.html` от Plesk.
3. **Upload** → выбрать оба файла из `load/agsk-3/`.

**Вариант B — FTP (быстрее для обновлений):**
```bash
# Пример через curl-ftp (хост/логин из письма)
curl -T load/agsk-3/index.html ftp://FTP_HOST/httpdocs/ --user LOGIN:PASS
curl -T load/agsk-3/logo.png   ftp://FTP_HOST/httpdocs/ --user LOGIN:PASS
```

## Шаг 5. Проверка

- Открыть в браузере: `https://baikulov-k-i.kz/` — должна появиться страница AGSK-3.
- Проверить SSL: замок в адресной строке, сертификат Let's Encrypt.
- **Проверка ЕШДИ:** https://checkip.sts.kz/ → ввести `baikulov-k-i.kz` → ожидаемый статус: **«доступ разрешён»**.
- С рабочего компа Госэкспертизы: зайти на `https://baikulov-k-i.kz/` — должно открыться без блокировки.

## Шаг 6. Почта `@baikulov-k-i.kz`

В Plesk → **Mail** → **Create Email Address**:
- Адрес: `k.baikulov@baikulov-k-i.kz` (или любой другой)
- Пароль: сгенерировать
- Mailbox size: 1 GB хватит

Настройка в клиенте (Thunderbird / мобильный):
- **IMAP:** `mail.baikulov-k-i.kz`, порт `993`, SSL/TLS
- **SMTP:** `mail.baikulov-k-i.kz`, порт `465`, SSL/TLS
- Логин: полный email, пароль — из Plesk

DNS для почты Plesk обычно создаёт сам (MX, SPF, DKIM). Проверить: `nslookup -type=mx baikulov-k-i.kz`.

## Шаг 7. Редирект со старого домена (опционально)

Если нужно, чтобы старые ссылки `agsk-3.baikulov-k.com` вели на новый:
- В Vercel dashboard → проект AGSK-3 → **Settings** → **Domains** → добавить redirect на `https://baikulov-k-i.kz/`.
- Или заменить `vercel.json` на `{"redirects": [{"source": "/(.*)", "destination": "https://baikulov-k-i.kz/$1", "permanent": true}]}`.

## Шаг 8. Синхронизация при обновлениях

Когда меняешь контент — правь локально в `load/agsk-3/`, затем заливай в `httpdocs/`.
Если контент меняется через Vercel (прод на `.com` ещё жив), перед заливкой повторно выкачать:
```bash
bash scripts/mirror_agsk3.sh
```

---

## Ожидаемые итоги

| Параметр          | До                                  | После                       |
|-------------------|-------------------------------------|-----------------------------|
| Домен             | `agsk-3.baikulov-k.com`             | `baikulov-k-i.kz`           |
| Хостинг           | Vercel (AWS US, Walnut CA)          | hoster.kz (Plesk, РК)       |
| IP сервера        | `216.198.79.65` (Amazon US)         | `<kz-ip>` (РК)              |
| SSL               | Vercel (Let's Encrypt)              | Let's Encrypt (Plesk)       |
| Проход через ЕШДИ | ❌ блок по ППРК №832                | ✅ открывается              |
| Почта             | нет                                 | `k.baikulov@baikulov-k-i.kz`|

**Время на всё:** ~2 часа (оплата хостинга + DNS + заливка + SSL).
