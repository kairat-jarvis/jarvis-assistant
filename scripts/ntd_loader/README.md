# ntd_loader

Загрузчик НТД из PDF в локальный `expertise_ntd` (Postgres + pgvector).
Заменяет удалённый n8n-workflow «НТД Консультант».

## Pipeline

```
PDF
 └── vypiska_ird.ocr_waterfall.extract_pdf     (L1 pdfplumber → L2 PaddleOCR-VL-1.5 → L3 Claude Vision)
      └── parser.parse_clauses                  (текст → клозы с clause_no/section_path)
           └── OpenAI text-embedding-3-small    (batched, 64 шт. на запрос)
                └── pg_store.upsert_*           (ntd_documents + clause_vectors)
                     └── journal.*              (SQLite: data/ntd_ingest.db)
```

Контракт схемы clause_vectors — см. `db/REDIRECT.md` и
auto-memory `reference_ntd_local_vs_supabase.md`.

## Зависимости

Уже стоят в проекте:

- `psycopg[binary]>=3.1`, `openai`, `pdfplumber`, `pdf2image`, `Pillow`
- PaddleOCR-VL-1.5 — только если PDF содержит сканы (см. `OCR.md`)
- `OPENAI_API_KEY` и (опционально) `NTD_PG_URL` в `.env`

## CLI

```bash
# Загрузка одного PDF (doc_code определится из текста)
python -m scripts.ntd_loader /path/to/СН_РК_4.04-07-2023.pdf

# Батч из директории
python -m scripts.ntd_loader docs/*.pdf

# Dry-run — только парсинг, без OpenAI и Postgres
python -m scripts.ntd_loader file.pdf --dry-run

# Явный doc_code, если автодетект не сработал
python -m scripts.ntd_loader file.pdf --doc-code "СН РК 1.04-26-2011"

# Принудительная перезагрузка (по умолчанию sha256-дубль пропускается)
python -m scripts.ntd_loader file.pdf --force

# Журнал
python -m scripts.ntd_loader --list
python -m scripts.ntd_loader --show <run_id>
```

## SQLite-журнал

Файл: `scripts/ntd_loader/data/ntd_ingest.db` (WAL-режим).
Схема: `db/schema.sql`. Таблицы:

| Таблица   | Назначение                                                                      |
| --------- | ------------------------------------------------------------------------------- |
| `runs`    | Один прогон = одна строка. status: running\|ok\|error\|skipped, sha256 PDF, агрегаты. |
| `pages`   | Постраничный tier (pdfplumber/paddleocr/claude-vision), confidence, fallback_reason. |
| `clauses` | Каждый upsert-нутый клоз: clause_pg_id, content_sha256, status.                 |
| `errors`  | Ошибки по фазам (extract/parse/embed/store).                                    |

Использование паттерна — `expertise-orchestrator/db/store.ts` (PRAGMA WAL,
`CREATE TABLE IF NOT EXISTS`, ленивый singleton, ON CONFLICT DO UPDATE).
См. auto-memory `feedback_chat_logs_sqlite.md`.

## Идемпотентность

- **PDF**: по `sha256` файла. Повторный прогон того же файла со статусом `ok` пропускается
  (см. `--force` для override).
- **ntd_documents**: по `doc_code` (UPDATE meta, не вставляет дубль).
- **clause_vectors**: id = `{doc_id}-{clause_no}`, `ON CONFLICT DO UPDATE` —
  безопасно перезагружать.

## Что не делается (намеренно)

- **Не пишет в Supabase** — только в локальный Postgres (см. `db/REDIRECT.md`).
- **Не использует другие OCR-движки** кроме разрешённых waterfall'ом
  (см. `CLAUDE.md → Извлечение текста из PDF`).
- **Не хранит сами клозы в SQLite** — только хэши и статусы; полный текст
  и embedding в Postgres.

## Известные ограничения

1. Парсер клозов работает на регулярках по началу строки `^\\d+(\\.\\d+){0,4}`.
   Документы с нестандартной нумерацией (`§ 5`, `Статья 5`) пока не поддерживаются.
2. Doc_code определяется по первым ~3000 символам. Если титульный лист — скан низкого
   качества, передавайте `--doc-code` вручную.
3. Год документа берётся как первый встретившийся 4-значный год — может быть неточным,
   проверяйте через `--show <run_id>`.
