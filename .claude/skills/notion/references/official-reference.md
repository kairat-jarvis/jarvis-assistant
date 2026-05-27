# Notion — official reference (distilled from help.notion.com and developers.notion.com)

Source pages:
- Help — Formulas: https://www.notion.com/help/formulas
- Help — Formula syntax: https://www.notion.com/help/formula-syntax
- Help — Databases intro: https://www.notion.com/help/intro-to-databases
- Developers — Getting started: https://developers.notion.com/docs/getting-started
- Developers — 2025-09-03 upgrade: https://developers.notion.com/docs/upgrade-guide-2025-09-03

When in doubt about a function signature, property payload, or endpoint path, **go to the source** — this file summarizes but doesn't replace the originals.

---

## 1. Formula language 2.0 — complete function index

### Operators

| Category | Operators |
|---|---|
| Arithmetic | `+` `-` `*` `/` `%` (modulo) `^` (exponentiation) |
| Comparison | `==` `!=` `<` `>` `<=` `>=` |
| Logical | `and` / `&&`, `or` / `\|\|`, `not` / `!` |
| Ternary | `condition ? then : else` |

### Data types

Text · Number · Boolean · Date · Person · Page (list) · List.

Lists support chained method syntax: `prop("Tags").length()`, `prop("Items").filter(current > 0).sum()`.

### Control flow

| Function | Signature | Example |
|---|---|---|
| `if` | `if(condition, then, else)` | `if(empty(prop("X")), 0, prop("X"))` |
| `ifs` | `ifs(cond1, val1, cond2, val2, ..., default)` | `ifs(x > 10, "big", x > 5, "mid", "small")` |
| `let` | `let(var, value, body)` | `let(x, 5 + 3, x * 2)` |
| `lets` | `lets(v1, e1, v2, e2, ..., body)` | `lets(a, "hi", b, "!", a + b)` |
| `empty` | `empty(value)` | `empty(prop("Note"))` |

### Text

| Function | Example | Result |
|---|---|---|
| `length(text)` | `length("hello")` | `5` |
| `substring(text, start, end?)` | `substring("Notion", 0, 3)` | `"Not"` |
| `contains(text, query)` | `contains("Notion", "ot")` | `true` |
| `test(text, regex)` | `test("Notion", "Not")` | `true` |
| `match(text, regex)` | `match("Notion Notion", "Not")` | `["Not", "Not"]` |
| `replace(text, regex, rep)` | `replace("Notion Notion", "N", "M")` | `"Motion Notion"` |
| `replaceAll(text, regex, rep)` | `replaceAll("Notion Notion", "N", "M")` | `"Motion Motion"` |
| `lower(text)` | `lower("NOTION")` | `"notion"` |
| `upper(text)` | `upper("notion")` | `"NOTION"` |
| `repeat(text, n)` | `repeat("0", 4)` | `"0000"` |
| `trim(text)` | `trim(" hi ")` | `"hi"` |
| `link(label, url)` | `link("Notion", "https://notion.so")` | clickable link |
| `style(text, format, color?)` | `style("Notion", "b", "blue")` | bold blue "Notion" |
| `unstyle(text, style?)` | `unstyle(x, "b")` | drops bold |
| `format(value)` | `format(1234)` | `"1234"` |
| `concat(a, b, ...)` | `concat("A", "B")` | `"AB"` (also works on lists) |

Style format letters: `b` bold, `i` italic, `u` underline, `s` strikethrough, `c` code. Colors: `default`, `gray`, `brown`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `red`.

### Math

| Function | Example | Result |
|---|---|---|
| `add(a, b)` | `add(5, 10)` | `15` |
| `subtract(a, b)` | `subtract(5, 10)` | `-5` |
| `multiply(a, b)` | `multiply(5, 10)` | `50` |
| `divide(a, b)` | `divide(5, 10)` | `0.5` |
| `mod(a, b)` | `mod(5, 10)` | `5` |
| `pow(base, exp)` | `pow(5, 10)` | `9765625` |
| `min(...)` | `min(1, 2, 3)` | `1` |
| `max(...)` | `max(1, 2, 3)` | `3` |
| `sum(...)` | `sum(1, 2, 3)` | `6` |
| `median(...)` | `median(1, 2, 4)` | `2` |
| `mean(...)` | `mean(1, 2, 3)` | `2` |
| `abs(n)` | `abs(-10)` | `10` |
| `round(n, dec?)` | `round(1.234, 2)` | `1.23` |
| `ceil(n)` | `ceil(0.4)` | `1` |
| `floor(n)` | `floor(0.4)` | `0` |
| `sqrt(n)` | `sqrt(4)` | `2` |
| `cbrt(n)` | `cbrt(64)` | `4` |
| `exp(x)` | `exp(1)` | `2.718…` |
| `ln(n)` | `ln(2.718)` | `≈1` |
| `log10(n)` | `log10(100000)` | `5` |
| `log2(n)` | `log2(1024)` | `10` |
| `sign(n)` | `sign(-10)` | `-1` |
| `pi()` | `pi()` | `3.14159…` |
| `e()` | `e()` | `2.71828…` |
| `toNumber(value)` | `toNumber("2")` | `2` |

### Date / time

| Function | Example | Result / notes |
|---|---|---|
| `now()` | `now()` | current datetime |
| `today()` | `today()` | current date (no time) |
| `minute(d)` / `hour(d)` | `hour(parseDate("...T17:35Z"))` | `17` |
| `day(d)` | `day(parseDate("2023-07-10"))` | `1` (Monday=1 per official example) |
| `date(d)` | `date(parseDate("2023-07-10"))` | `10` (day-of-month) |
| `week(d)` | `week(parseDate("2023-01-02"))` | `1` |
| `month(d)` / `year(d)` | `year(now())` | current year |
| `dateAdd(d, n, unit)` | `dateAdd(now(), 1, "days")` | units: years, quarters, months, weeks, days, hours, minutes |
| `dateSubtract(d, n, unit)` | `dateSubtract(now(), 2, "months")` | same units |
| `dateBetween(d1, d2, unit)` | `dateBetween(now(), parseDate("2022-09-07"), "days")` | `357` (d1 − d2) |
| `dateRange(start, end)` | — | creates a date range value |
| `dateStart(range)` / `dateEnd(range)` | `dateStart(prop("Range"))` | extract endpoints |
| `timestamp(d)` | `timestamp(now())` | Unix ms |
| `fromTimestamp(ms)` | `fromTimestamp(1689024900000)` | date from Unix ms |
| `formatDate(d, fmt)` | `formatDate(now(), "MMMM D, Y")` | Moment-style format string |
| `parseDate(iso)` | `parseDate("2022-01-01")` | date from ISO string |

> **Gotcha for API-set formulas:** `parseDate("...")` returns a date that fails strict equality against property-dates in `dateBetween`. Use `fromTimestamp(ms)` for date constants in formulas written via API. See `references/formulas-gotchas.md`.

### Lists

| Function | Example | Result |
|---|---|---|
| `at(list, i)` | `at([1,2,3], 1)` | `2` |
| `first(list)` / `last(list)` | `first([1,2,3])` | `1` |
| `slice(list, start, end?)` | `slice([1,2,3], 1, 2)` | `[2]` |
| `concat(l1, l2)` | `concat([1,2], [3,4])` | `[1,2,3,4]` |
| `sort(list)` / `reverse(list)` | `sort([3,1,2])` | `[1,2,3]` |
| `join(list, sep)` | `join(["a","b"], ", ")` | `"a, b"` |
| `split(text, sep)` | `split("a,b", ",")` | `["a","b"]` |
| `unique(list)` | `unique([1,1,2])` | `[1,2]` |
| `includes(list, v)` | `includes(["a","b"], "b")` | `true` |
| `find(list, cond)` | `find(["a","b"], current == "b")` | `"b"` |
| `findIndex(list, cond)` | `findIndex(["a","b"], current == "b")` | `1` |
| `filter(list, cond)` | `filter([1,2,3], current > 1)` | `[2,3]` |
| `some(list, cond)` | `some([1,2,3], current == 2)` | `true` |
| `every(list, cond)` | `every([1,2,3], current > 0)` | `true` |
| `map(list, expr)` | `map([1,2,3], current + 1)` | `[2,3,4]` |
| `flat(list)` | `flat([[1,2],[3,4]])` | `[1,2,3,4]` |

Inside list lambdas, the element is bound to the keyword `current`.

### People and pages

| Function | Example |
|---|---|
| `name(person)` | `name(prop("Created by"))` |
| `email(person)` | `email(prop("Created by"))` |
| `id(page?)` | `id()` — current page's ID; `id(prop("Rel").first())` — linked page's ID |

### Property access

`prop("PropertyName")` is the sole access method. Names are case-sensitive and must match the DB schema exactly (including digit prefixes, spaces, mixed Cyrillic/Latin). For select / status, `prop()` returns the name as a string.

### What's NOT supported

- Iterative loops (`for`, `while`) — use `map` / `filter` / `reduce`-like list operations.
- Random number generation (no `random()` or equivalent).

---

## 2. Database fundamentals

### Property types

Property types (use these strings exactly in API payloads):

`title`, `rich_text`, `number`, `select`, `multi_select`, `status`, `date`, `people`, `files`, `checkbox`, `url`, `email`, `phone_number`, `formula`, `relation`, `rollup`, `created_time`, `created_by`, `last_edited_time`, `last_edited_by`, `unique_id` (auto-incrementing, useful for project codes), `verification` (page verification status), `button` (manual-trigger automation).

Notes:
- `select` has a flat list of options; `status` has options grouped into lifecycle buckets (To-do / In progress / Complete), which surfaces nicely in kanban boards and filters.
- `relation` replaces the old database-to-database link; in API 2025-09-03 the target is a **data_source_id**, not a database_id.
- `rollup` aggregates a relation's column via count / sum / min / max / avg / earliest_date / latest_date / etc. A rollup cannot reference another rollup directly — chain via an intermediate formula if you need it.

### Views

`table`, `list`, `board`, `calendar`, `gallery`, `timeline`. The same DB can host multiple views, each with its own filters, sorts, and visible properties.

### Full-page vs inline

- **Full-page**: shows as an independent sidebar entry, supports locking.
- **Inline**: embedded in a parent page, controls hidden until hover. Most personal workspaces default to inline; most production dashboards use full-page.

### Filters and sorts

Filter operators come from the filter schema (see `api-cheatsheet.md`). Common ones:
- Text: `equals`, `does_not_equal`, `contains`, `does_not_contain`, `starts_with`, `ends_with`, `is_empty`, `is_not_empty`.
- Number: `equals`, `greater_than`, `less_than`, `greater_than_or_equal_to`, `less_than_or_equal_to`, `is_empty`, `is_not_empty`.
- Date: `equals`, `before`, `after`, `on_or_before`, `on_or_after`, `past_week`, `past_month`, `past_year`, `next_week`, etc.
- Select / status: `equals`, `does_not_equal`, `is_empty`, `is_not_empty`.
- Combine with `and` / `or` — can nest.

---

## 3. API 2025-09-03 — what changed and why

The database concept was split into:
- **Database** — container with title, icon, cover, parent, inline flag.
- **Data source(s)** — schema + rows. A database holds one or more data sources.

**Before** (pre-2025-09-03): everything lived at `/v1/databases/{id}`.
**After**: most per-row / per-property operations moved to `/v1/data_sources/{ds_id}`.

### Endpoint migration map

| Operation | Old | New |
|---|---|---|
| Get DB metadata | `GET /v1/databases/{id}` | same — now includes `data_sources[]` |
| Get schema | `GET /v1/databases/{id}` returned `properties` | `GET /v1/data_sources/{ds_id}` |
| Update schema / properties | `PATCH /v1/databases/{id}` | `PATCH /v1/data_sources/{ds_id}` |
| Update DB attributes (title, icon) | same — `PATCH /v1/databases/{id}` | unchanged |
| Query rows | `POST /v1/databases/{id}/query` | `POST /v1/data_sources/{ds_id}/query` |
| Create page with DB parent | `parent: { database_id: id }` | `parent: { data_source_id: ds_id }` |
| Relation property definition | `relation: { database_id: ... }` | `relation: { data_source_id: ... }` |

### How to discover `data_source_id`

```python
db = GET /v1/databases/{database_id}
ds_id = db["data_sources"][0]["id"]   # default/only data source for a single-source DB
```

Always cache this — every script session should resolve it once and reuse.

### Mixed responses (read vs write)

For relation property objects: **reads include both `database_id` and `data_source_id`** (back-compat), but **writes must include only `data_source_id`**. If you round-trip a payload, strip `database_id` before PATCHing.

### Webhook events added

`data_source.created`, `data_source.schema_updated`, `data_source.content_updated`, `data_source.moved`, `data_source.deleted`, `data_source.undeleted`. Subscribe to these if you have integrations that react to schema changes.

---

## 4. Authentication

### Internal connection (what this project uses)

1. https://www.notion.com/profile/integrations → create integration → **Internal**.
2. Grant capabilities (Read content, Insert content, Update content). Don't grant more than needed.
3. Copy `Internal Integration Secret` (starts with `ntn_` or `secret_`).
4. On each database / page the integration should access, click `···` → Connections → Add the integration. **Being connected to a parent page is not enough** — the target database itself must have the connection.

Bearer auth header: `Authorization: Bearer ntn_...`

### Public / OAuth connection

For multi-workspace integrations (marketplace apps). Users authorize via Notion's OAuth flow and pick which pages to grant access to. Use this only when building something others will install.

---

## 5. Request limits

Notion rate-limits to roughly **3 requests per second** per integration (subject to change — check https://developers.notion.com/reference/request-limits for current numbers). On 429, respect the `Retry-After` header.

Payload limits (approximate, from docs):
- Property text: 2000 chars per rich-text segment.
- Formula expression: several KB (practical test: 8 KB stored expressions work).
- Relation targets per property: up to 100 per request when setting.
- Array properties (multi_select, people, files, relation): up to 100 entries per property per page.

---

## 6. Further reading

- Changelog: https://developers.notion.com/changelog
- OpenAPI spec: https://developers.notion.com/openapi.json
- Filter schema: https://developers.notion.com/reference/post-database-query-filter
- Property object: https://developers.notion.com/reference/property-object
- Pagination: https://developers.notion.com/reference/intro#pagination
