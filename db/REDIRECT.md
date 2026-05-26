# Supabase → локальный PostgreSQL: план редиректа

> **Статус на 2026-05-26.** НТД полностью переехала в локальный PG; Supabase-таблицы
> `ntd_documents` и `clause_vectors` обнулены (`TRUNCATE`), n8n-workflow «НТД Консультант»
> (`ntd_wf.json`) удалён. Облачный workflow `oQvQ5TEZU5ypM1SU` в `kairat679.app.n8n.cloud`
> ещё активен — деактивировать вручную в UI n8n.cloud. Загрузчик новой НТД в локальный PG
> ещё не написан (TBD).

## Архитектура после миграции

- **Единственный источник истины НТД**: `postgresql://localhost/expertise_ntd`
  (395 документов, 90 368 клозов на момент последнего успешного запроса).
  Схема, индексы, RPC — `PROGRAMMING/expertise-orchestrator/db/ntd-schema.sql`.
  Cloud-зеркало больше не поддерживается.
- **Источник истины JARVIS-памяти**: `postgresql://localhost/jarvis_local`.
  Схема — `db/jarvis-schema.sql`. RPC `match_jarvis_memory`/`get_jarvis_stats` совместимы
  с Supabase, плюс локально-специфичный `hybrid_search_jarvis_memory` (BM25+cosine RRF).
- **Supabase остаётся только для `jarvis_memory`** — туда пишут оставшиеся n8n cron-workflow
  (AI-мониторинг, дайджесты), оттуда периодически синкаемся в локальный PG. НТД-таблицы
  в Supabase пустые и больше не используются; не удалены (схема стоит), чтобы при возврате
  можно было залить заново.

## Клиенты

| Слой | Файл | Что заменяет |
|---|---|---|
| НТД | `scripts/ntd_local.py` (`NtdLocal`) | `supabase.rpc('match_clauses')`, `hybrid_search_clauses`, `fts_only_search_clauses` |
| JARVIS | `scripts/jarvis_local.py` (`JarvisLocal`) | `supabase.rpc('match_jarvis_memory')`, `get_jarvis_stats`; добавляет `hybrid_search`, `fts_only` |
| Миграция (jarvis-memory) | `scripts/migrate_jarvis_from_supabase.py` | разовая/периодическая синхронизация Supabase → local для `jarvis_memory` |
| Загрузчик НТД | _TBD_ | замена удалённого n8n-чата «НТД Консультант». Должен наполнять локальный `expertise_ntd` (а не Supabase). |

## Что редиректим

Уже переписано на локальный PG (2026-05-26):

- `JARVIS ASSISTANT/scripts/ntd_ask_with_review.py`, `cv_label.py`, `export_pretrain_dataset.py`
- `Claude Assistant/projects/drawings-core/pipeline/norm_enricher.py`
- `КРАКЕН/tools/lookup_ntd.py` (плюс `psycopg[binary]` в `requirements.txt`)

Остальные кандидаты на проверку (если ещё ходят в Supabase NTD — сейчас вернут пустоту):

- `scripts/check_pd_section.py`
- `scripts/pd_check_setup.py`
- `scripts/generate_pd_prompts_krakin.py`

Не редиректим:

- `scripts/update_tts_supabase.py` — это Supabase Storage (bucket), локального аналога нет.

## Что НЕ редиректим из n8n

**Остаются на Supabase (только `jarvis_memory` / `jarvis_agent_logs`)**:
`JARVIS_AI_Monitor.json`, `JARVIS_Notion_Sync.json`, `JARVIS_Router.json`,
`JARVIS_Voice_Search.json`, `JARVIS_Vision_2oo3.json`, `JARVIS_YouTube_Monitor.json`.

Причина: n8n крутится в `kairat679.app.n8n.cloud` и не достучится до `localhost:5432`
без Cloudflare Tunnel / Tailscale Funnel. Это отдельная задача — пока не решено,
n8n пишет в Supabase, локально вытягиваем `migrate_jarvis_from_supabase.py --from-supabase`.

**Удалён** (2026-05-26): `ntd_wf.json` (workflow «НТД Консультант»). Cloud-инстанция
этого workflow в n8n.cloud остаётся активной — после удаления Supabase-данных она
возвращает пустые ответы. Деактивировать в UI n8n.cloud (id `oQvQ5TEZU5ypM1SU`).

## .env

```env
# Локальные БД — приоритет
NTD_PG_URL=postgresql://localhost/expertise_ntd
JARVIS_PG_URL=postgresql://localhost/jarvis_local

# Supabase — остаётся для jarvis_memory n8n-cron + миграции
SUPABASE_URL=https://omykcphkzmmqpwswwfsw.supabase.co
SUPABASE_PROJECT_ID=omykcphkzmmqpwswwfsw
# SUPABASE_SERVICE_ROLE_KEY=...   # только для миграции через PostgREST
```

## Регламент синхронизации

1. **JARVIS-память (n8n → Supabase → local)**: периодически запускаем
   `.venv/bin/python scripts/migrate_jarvis_from_supabase.py --from-supabase`.
   Идемпотентно (ON CONFLICT DO UPDATE).
2. **Схема JARVIS**: править `db/jarvis-schema.sql` + `setup_supabase.sql` синхронно,
   применять к обеим БД (`psql jarvis_local -f ...` и Supabase migration).
3. **НТД**: источник истины — **локальный** `expertise_ntd`. Cloud-mirror отключён.
   Когда появится новый загрузчик (вместо удалённого n8n-чата) — он должен писать
   напрямую в локальный PG, а не в Supabase.

## Проверка работоспособности

```bash
# НТД
.venv/bin/python scripts/ntd_local.py
# JARVIS
.venv/bin/python scripts/jarvis_local.py
```

## История изменений

- **2026-05-26**: НТД ушла полностью с Supabase. Очищены `ntd_documents` (395 → 0) и
  `clause_vectors` (90 368 → 0). Удалён `n8n_workflows/ntd_wf.json`. Переписаны
  `norm_enricher.py` (drawings-core) и `lookup_ntd.py` (КРАКЕН) на локальный PG.
  Embedding-модель в обоих файлах поднята с `text-embedding-ada-002` до
  `text-embedding-3-small` (БД заполнена 3-small'ом; ada-002 ломал cosine).
