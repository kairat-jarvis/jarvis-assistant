---
name: notion
description: Work with Notion databases, formulas, and API — adding/updating properties, writing formula expressions (dateBetween, fromTimestamp, let, day), querying data sources, setting up integrations. Use this skill whenever the user mentions Notion, a Notion database/workspace, Notion formulas, Notion-Version API headers, "data_sources", property types (select/status/relation/formula/rollup), or asks to compute working days / deadlines / KPI metrics in Notion — even if they don't explicitly say "use the notion skill". Also trigger on Russian cues like «база Notion», «формула Notion», «свойства базы», «рабочих дней с учётом праздников», or mentions of the JARVIS project's «Проекты Экспертиза» base.
---

# Notion — databases, formulas, API

This skill captures what works (and what silently breaks) when automating Notion. Before experimenting on formula syntax or endpoint shapes, **consult the reference first** — random iteration is slow because Notion's error messages ("Type error with formula") don't pinpoint causes.

Reference order (cheapest → deepest):
1. `references/official-reference.md` — distilled from help.notion.com + developers.notion.com; complete function index, property types, API endpoint map. Start here.
2. `references/formulas-gotchas.md` — known runtime quirks that contradict or extend the official docs (e.g. `let()` can't bind date props, `parseDate` vs `fromTimestamp` for constants).
3. `references/api-cheatsheet.md` — request/response payload shapes, error codes, pagination.
4. `references/holidays-kz.md` — Kazakhstan public-holiday data for working-day formulas.
5. Live docs — https://www.notion.com/help and https://developers.notion.com — for the current year's changes, SDK updates, and anything not yet captured above.

## Decide the path first

When the user asks for something Notion-related, identify which of these they need. Each has a different workflow below.

| User asks for… | Go to |
|---|---|
| Add / rename / change type of properties in a DB | [Modify schema via API](#modify-schema-via-api) |
| Write a formula (deadlines, working days, status flags) | [Writing formulas](#writing-formulas) |
| Read / query existing pages | [Querying data](#querying-data) |
| Set up a new integration / MCP connection | [Integration setup](#integration-setup) |
| Understand a function you haven't used before | `references/official-reference.md` §1 (formulas) or §2 (databases) |
| Understand why something broke | `references/formulas-gotchas.md` + `references/api-cheatsheet.md` |

## Integration setup

Notion integration token + database ID are needed for API access. In this project they live in `.env` at the repo root:

```
NOTION_TOKEN=ntn_...          # Internal Integration Secret
NOTION_DATABASE_ID=...        # 32-char hex from the base URL
```

Getting them:
1. https://www.notion.com/profile/integrations → create / open integration → copy Internal Integration Secret.
2. **Critical**: connect the integration to the *specific database* via the DB's `···` menu → Connections → Add connection. Being connected only to a parent page is not enough — the API will return 404 on the DB ID.
3. Database ID is the 32-char string in the URL: `https://www.notion.so/<workspace>/<DATABASE_ID>?v=...`.

If the user pastes a Notion URL, extract the ID for them automatically.

## Modify schema via API

**Always use this exact combination** for any property-touching call:

- Endpoint: `PATCH /v1/data_sources/{data_source_id}` (**not** `/v1/databases/{id}` — that endpoint no longer accepts property edits in recent versions)
- Header: `Notion-Version: 2025-09-03`

Resolve `data_source_id` first:

```python
db = GET /v1/databases/{NOTION_DATABASE_ID}    # with Notion-Version: 2025-09-03
ds_id = db["data_sources"][0]["id"]
```

Then PATCH the data source with the properties payload. Example shapes:

```python
# URL field
"Ссылка на папку": {"url": {}}

# Select with options
"Класс объекта": {"select": {"options": [{"name": "Ф1.1"}, {"name": "Ф3.1"}]}}

# Formula
"Дней до дедлайна": {"formula": {"expression": "dateBetween(prop(\"Дедлайн\"), now(), \"days\")"}}

# Relation to another DB's data_source
"Связанный проект": {"relation": {"data_source_id": "<other_ds_id>", "single_property": {}}}
```

Idempotency: Notion PATCH with an existing property name **updates it in place** rather than erroring. Before adding new properties, GET the current schema and filter out names that already exist if you want to avoid surprise updates.

**Dangerous updates on `select` / `multi_select` / `status`:**
- When you PATCH an option list, the payload is **replace-whole-list**, not merge. Options that exist in the DB but are **omitted** from your payload get deleted — along with any data on rows using them. Always GET first, merge new options onto the existing list, and PATCH back the union.
- Existing options are identified by their `id`, not their `name`. To rename an option via API, include the existing `id` in your payload. Changing only `name` without `id` creates a new option and drops the old one.
- `status`-property **groups** (To-do / In progress / Complete) cannot be configured via the API. Create or restructure groups in the Notion UI.

**Existing scripts in this project** (study before writing new ones — they're project-local, not bundled with the skill):
- `scripts/notion_add_project_fields.py` (project root) — adds 6 fields to «Проекты Экспертиза». Historical note: this script still uses the legacy `PATCH /v1/databases/{id}` with `Notion-Version: 2022-06-28` and happened to work for URL/Select/Formula types. New scripts should use the `data_sources` endpoint described above.
- `scripts/notion_update_expertise_workdays.py` (project root) — uses the modern pattern (`/v1/data_sources/{ds_id}`, `2025-09-03`) to rewrite the working-days formula.

Full endpoint list with example payloads: `references/api-cheatsheet.md`.

## Writing formulas

Notion Formula 2.0 is stricter about types than it looks. The three rules below are non-obvious and each cost time in this project:

### Rule 1 — `let()` cannot bind date-valued expressions

This **fails** with `Type error with formula`:

```
let(d, prop("Дата_начала"), dateBetween(d, now(), "days"))       # WRONG
let(x, dateBetween(prop("A"), prop("B"), "days"), x + 1)         # WRONG
```

The runtime refuses to bind a date property or a `dateBetween` result to a `let` variable, even though it type-checks as a number. Workaround: **inline the date expression** everywhere it's used, even if that means computing `dateBetween(...)` three times. `let()` still works fine for pure numeric literals and computed numbers that never touched a date property.

```
# Right — inline instead of binding
(dateBetween(prop("A"), prop("B"), "days") + 1)
  - 2 * floor((dateBetween(prop("A"), prop("B"), "days") + 1) / 7)
  - ...
```

### Rule 2 — Use `fromTimestamp(ms)`, not `parseDate("…")`, for date constants

`parseDate("2026-01-01")` returns a date whose internal type can't be compared with a property-date via `dateBetween` — same "Type error" as Rule 1. `fromTimestamp(ms)` returns a type-compatible date.

```
# WRONG — parseDate is not comparable to a prop date
dateBetween(parseDate("2026-01-01"), prop("Дата"), "days")

# RIGHT — compute Unix ms (UTC midnight) in your generator script
dateBetween(fromTimestamp(1767225600000), prop("Дата"), "days")
```

Use `scripts/compute_holiday_ms.py` (in this skill's `scripts/`) to generate timestamps for a list of dates. For RK 2026 holidays the list is already in `references/holidays-kz.md`.

### Rule 3 — Always guard against empty dates

A formula that reads an empty date property returns an invisible error value that breaks downstream math. Wrap date formulas in an empty-guard:

```
if(empty(prop("Дата")), toNumber(""),
  dateBetween(prop("Дата"), now(), "days")
)
```

`toNumber("")` yields a blank number, which Notion displays as empty — cleaner than `0` for missing data.

### Formula templates

Common patterns, copy-paste-ready:

**Days until deadline (with guard)**
```
if(empty(prop("Дедлайн")), toNumber(""),
   dateBetween(prop("Дедлайн"), now(), "days"))
```

**Overdue? (checkbox-valued)**
```
not empty(prop("Дата_ответа"))
and prop("Дата_ответа") < now()
and prop("Status") != "Положительно"
```

**Calendar-days duration between two date properties**
```
if(empty(prop("Начало")) or empty(prop("Конец")), toNumber(""),
   dateBetween(prop("Конец"), prop("Начало"), "days"))
```

**Working days between two date properties (with RK holidays)**

This is the complex case and worth its own reference. See `references/formulas-gotchas.md` §«Working days formula» for the full generated expression and the math behind the weekend subtraction. The idea:

- `total = dateBetween(end, start, "days") + 1` (inclusive)
- `dow = day(start)` — 0=Sunday … 6=Saturday
- `w = floor(total / 7)`, `r = total - 7*w`
- Sunday in r: `(7 - dow) % 7 < r`
- Saturday in r: `(13 - dow) % 7 < r`
- weekends = `2*w + sun + sat`
- holidays = sum of `fromTimestamp(ms)`-based range checks for each holiday
- answer = `total - weekends - holidays`

For 2026 the project uses `scripts/notion_update_expertise_workdays.py`. When a new year's RK calendar is published, update `RK_HOLIDAYS_2026` → `RK_HOLIDAYS_2027` in that script and rerun.

### day() day-of-week convention

Notion's official docs show `day(parseDate("2023-07-10")) == 1` and July 10 2023 was a Monday, so Monday is encoded as 1. The docs are less explicit about Sunday; common conventions are either 0 (Sunday … Saturday = 0..6) or 7 (ISO: Monday … Sunday = 1..7). **The weekend math in `formulas-gotchas.md` works for either convention** because it operates mod 7 — `(7 − dow) % 7` and `(13 − dow) % 7` give the same answer whether Sunday is 0 or 7. Don't sweat the ambiguity; just keep the math as written.

### Styling text output (`style`, `link`, `concat`)

For formulas that produce user-visible text (status badges, flags, KPI labels), use `style()`:

```
style(text, format, color?)
```

Format letters: `b` bold, `i` italic, `u` underline, `s` strikethrough, `c` code. Colors: `default`, `gray`, `brown`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `red`, plus `*_background` variants (`blue_background`, `yellow_background`, …) for highlight colors. Color is optional.

```
style("🔴 Просрочено", "b", "red")          # bold red
style("В работе", "i")                       # italic, default color
style("МОЙ", "b", "blue_background")         # bold with blue background
```

**`style()` gotcha**: Via the API, `style()` only accepts **pure-literal arguments**. Passing `prop("X")`, any string derived from a prop (`upper(prop("X"))`, `format(prop("X"))`, `"★ " + prop("X")`), or even a boolean result (`if(contains(prop(...), ...), style(...), style(...))`) raises `Type error with formula`. So conditional row-level highlighting **cannot** be achieved through `style()` via API.

Workarounds:
- **Visual marker column** — use a formula with emoji + CAPS markers (no `style()`): `if(contains(prop("X"), "Y"), "🟦 ВАЖНО", "")`. Works everywhere, sortable, filterable.
- **UI conditional formatting** — open the view, `···` → Filter & Sort → Conditional formatting → condition + bold + background color. Native per-row highlight, but requires a Team plan or higher.
- `style()` with pure literals works fine in headers/labels where the text is constant — it's only the prop-dependent case that fails.

Use `link(label, url)` for hyperlinks. Mixed styling in one cell is done via `concat()` of individually-styled literal segments.

### Empty output — numbers vs strings

- **Number-returning formula, "empty" result:** `toNumber("")` (yields blank, not 0).
- **String-returning formula, "empty" result:** `""` (empty string).
- **Boolean-returning:** `false` works; there's no "blank" boolean.

Don't use `toNumber("")` in a string formula — it changes the formula's output type and breaks downstream sorting/filtering.

### `now()` has time-of-day; `today()` does not

`now()` returns the current timestamp (date + time). `today()` returns midnight of the current date. For "due within N days" checks where deadline is a date-only property:

```
dateBetween(prop("Дедлайн"), now(), "days")
```

Notion truncates toward zero, so at 10 AM on the day of a date-only deadline, this returns `0`; next day it returns `-1`. For a symmetric "is today through +3 days inclusive" check, prefer `today()` over `now()` or compare via two conditions:

```
dateBetween(prop("Дедлайн"), today(), "days") >= 0
and dateBetween(prop("Дедлайн"), today(), "days") <= 3
```

### Operator precedence

Notion follows the conventional order: `not` > `^` > `*` `/` `%` > `+` `-` > comparison (`< <= > >= == !=`) > `and` > `or` > ternary `? :`. When in doubt, parenthesize — the extra chars are free, and one missing set is a full debugging loop.

### Status vs Select comparisons

Both `status` and `select` properties return their option name as a string in formulas, so `prop("Status") == "Done"` works the same for either type. `.name` is not needed (and not supported in formula 2.0). `empty(prop("Status"))` is `true` when nothing is selected.

### Formula size

Inline everything makes formulas long. The stored expression can be 2–8 KB — that's fine, the API accepts it. When Notion stores it, it replaces `prop("Name")` with internal block-property references (`{{notion:block_property:...}}`), so the stored length is larger than what you sent. Don't panic if a 3 KB send-length becomes 7 KB on read-back.

## Querying data

Read pages from a database using the **data source** query endpoint (again, not `/v1/databases/{id}/query`):

```
POST /v1/data_sources/{ds_id}/query
Headers: Notion-Version: 2025-09-03
Body: { "filter": {...}, "page_size": 10 }
```

Filters follow the standard Notion filter schema (see `references/api-cheatsheet.md`). Formula results come back as `{"formula": {"number": 45}}` or `{"formula": {"string": "..."}}` depending on output type.

## When something breaks

Before guessing, check `references/formulas-gotchas.md` — it lists the seven error messages you'll actually see (`Type error with formula`, `Parse error with formula`, `This API is deprecated`, etc.) with the real cause and the fix.

If the error isn't listed there, **go to the docs**: https://www.notion.com/help and https://developers.notion.com. Do not iterate randomly on formula syntax — the runtime doesn't give enough feedback to make trial-and-error efficient.

## Project-specific: «Проекты Экспертиза»

The JARVIS project has a Notion DB named **«Проекты Экспертиза»** (ID: `06bfaa978a1045d9902002806b466fc4`). Key properties:

- `Номер` (title) — РГП project number, e.g. `01-03/00004`
- `1-Начало`, `3-Ответ`, `6-45й Заключение` — date workflow milestones
- `Status` (type `status`, not `select`) — workflow state, "Положительно" = success
- `Ведущий эксперт`, `Проектировщик`, `Договор` — parties
- Added 2026-04-24: `Ссылка на папку Google Drive`, `Класс объекта по МОПБ` (Select Ф1.1…Ф5.3), `Дней до ответа` (formula), `Срок экспертизы, дней` (formula — working days RK 2026), `Просрочен?` (formula), `Замечания по проектам` (URL)

When the user references this database by name, use these property names as-is (they contain digits-prefixes and mixed-case Cyrillic). When writing formulas, double-check the exact spelling against a fresh GET — a typo in the property name is the most common silent failure.
