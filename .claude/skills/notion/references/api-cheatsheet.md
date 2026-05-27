# Notion API — endpoints, headers, payloads

## Current header policy (2025)

**Always send**: `Notion-Version: 2025-09-03` and `Authorization: Bearer ntn_...`.

Older versions (`2022-06-28` etc.) are partially deprecated for database mutations — some PATCHes silently no-op or return "This API is deprecated". If you inherit code with an older header, upgrade before debugging.

## Databases vs data_sources (2025-09-03 model)

Starting with version `2025-09-03`, Notion split a database into a **database container** (metadata, parent, icon, inline/full mode) and one or more **data sources** (the actual row schema: properties + pages). Most property-touching endpoints moved to `/v1/data_sources/...`.

Quick map:

| Task | Endpoint |
|---|---|
| Get database metadata | `GET /v1/databases/{database_id}` |
| List data sources inside a DB | `GET /v1/databases/{database_id}` → `.data_sources[]` |
| Get schema / properties | `GET /v1/data_sources/{ds_id}` |
| Add / rename / remove properties | `PATCH /v1/data_sources/{ds_id}` |
| Query rows | `POST /v1/data_sources/{ds_id}/query` |
| Create a row | `POST /v1/pages` with `parent: { data_source_id: ds_id }` |
| Update a row | `PATCH /v1/pages/{page_id}` |

Most databases have exactly one data_source — take `data_sources[0].id`. Multi-source databases exist for views that union rows from several sources.

## Minimal Python client (stdlib only)

```python
import json, urllib.request, urllib.error

NOTION_VERSION = "2025-09-03"

def call(method, path, token, body=None):
    url = f"https://api.notion.com/v1{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Notion {e.code}: {e.read().decode('utf-8', 'replace')}")

def resolve_ds_id(token, database_id):
    db = call("GET", f"/databases/{database_id}", token)
    return db["data_sources"][0]["id"]
```

## Property payload reference

Each property has a **type discriminator** (first key) and a type-specific body.

### Scalars

```python
"Title field":       {"title": {}}
"Plain text":        {"rich_text": {}}
"Number":            {"number": {"format": "number"}}   # or "currency", "percent", "kazakhstani_tenge", ...
"URL":               {"url": {}}
"Email":             {"email": {}}
"Phone":             {"phone_number": {}}
"Checkbox":          {"checkbox": {}}
"Created time":      {"created_time": {}}
"Last edited time":  {"last_edited_time": {}}
"Created by":        {"created_by": {}}
"Last edited by":    {"last_edited_by": {}}
```

### Selects

```python
"Single select": {
  "select": {
    "options": [
      {"name": "Option A", "color": "blue"},
      {"name": "Option B", "color": "green"}
    ]
  }
}

"Multi select": {"multi_select": {"options": [...]}}

# Status — different type; options are grouped
"Workflow": {
  "status": {
    "options": [{"name": "New"}, {"name": "Doing"}, {"name": "Done"}],
    "groups":  [
      {"name": "To-do",      "color": "gray",  "option_ids": [...]},
      {"name": "In progress","color": "blue",  "option_ids": [...]},
      {"name": "Complete",   "color": "green", "option_ids": [...]}
    ]
  }
}
```

Colors: `default`, `gray`, `brown`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `red`.

### Date

```python
"Deadline": {"date": {}}
```

### Relation

```python
"Related tasks": {
  "relation": {
    "data_source_id": "<ds_id-of-target-database>",
    "single_property": {}                # or "dual_property": {} for synced two-way
  }
}
```

Note the **`data_source_id`** field — in 2025-09-03 it's no longer `database_id`.

### Rollup

```python
"Sum of hours": {
  "rollup": {
    "relation_property_name": "Related tasks",
    "rollup_property_name":   "Hours",
    "function":               "sum"   # or count, min, max, average, earliest_date, latest_date, ...
  }
}
```

### Formula

```python
"Days until deadline": {
  "formula": {
    "expression": "if(empty(prop(\"Deadline\")), toNumber(\"\"), dateBetween(prop(\"Deadline\"), now(), \"days\"))"
  }
}
```

Escape double-quotes inside the JSON string. See `references/formulas-gotchas.md` for the formula syntax rules.

### People / Files

```python
"Assignee":    {"people": {}}
"Attachments": {"files": {}}
```

## Renaming / removing a property

Rename: send the old name as key, pass `{"name": "New name"}` as the body:
```python
{"properties": {"Old name": {"name": "New name"}}}
```

Remove: pass `null` as the body:
```python
{"properties": {"Old name": null}}
```

(JSON-encoded `null`, not the string "null".)

## Querying rows

```python
POST /v1/data_sources/{ds_id}/query
{
  "filter": { ... },          # optional — standard Notion filter
  "sorts":  [ {"property": "Number", "direction": "ascending"} ],
  "page_size": 100,           # max 100
  "start_cursor": "<cursor>"  # from previous response's next_cursor
}
```

Filter examples:

```python
# Equality on title
{"property": "Номер", "title": {"equals": "01-03/00004"}}

# Combined
{"and": [
  {"property": "Status", "status": {"equals": "В работе"}},
  {"property": "Deadline", "date": {"before": "2026-06-01"}}
]}

# Formula results can be filtered
{"property": "Days until deadline", "formula": {"number": {"less_than": 7}}}
```

## Reading a page's property back

After PATCH, Notion may rewrite property references — e.g. `prop("Name")` becomes an internal `{{notion:block_property:...}}` in the stored `formula.expression`. That's fine; the formula still works. If you want to **display** the human-readable form, it's not available via API — the stored expression is always the internal form.

For a formula property, the computed value on a row comes back as:
```python
row["properties"]["My Formula"] == {
  "id": "...",
  "type": "formula",
  "formula": {"type": "number", "number": 42}   # or "string" / "boolean" / "date"
}
```

## Pagination

Always check `response["has_more"]`. When `true`, fetch the next page with `start_cursor: response["next_cursor"]`. For a full dump:

```python
cursor = None
all_pages = []
while True:
    body = {"page_size": 100}
    if cursor: body["start_cursor"] = cursor
    r = call("POST", f"/data_sources/{ds_id}/query", token, body)
    all_pages.extend(r["results"])
    if not r["has_more"]: break
    cursor = r["next_cursor"]
```

## Common HTTP errors

- **400 `validation_error`** — usually a schema mismatch (wrong property type) or formula Parse/Type error (see `formulas-gotchas.md`)
- **401 `unauthorized`** — token wrong / revoked; regenerate in integration settings
- **404 `object_not_found`** — the integration isn't connected to that specific database. Fix via the DB's `···` → Connections → Add connection. Being connected to the parent page only is not enough
- **409 `conflict_error`** — concurrent edit; retry with backoff
- **429** — rate-limited; respect the `Retry-After` header (usually ~1–3 seconds)

## When in doubt

Authoritative API reference: https://developers.notion.com/reference/
Official changelog: https://developers.notion.com/changelog
Guides and tutorials: https://developers.notion.com/docs/getting-started
