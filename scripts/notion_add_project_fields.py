"""Add 6 new properties to Notion database 'Проекты Экспертиза'.

Usage:
    set NOTION_TOKEN=secret_xxx          (or ntn_xxx for new integrations)
    set NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python scripts/notion_add_project_fields.py

Or pass as args:
    python scripts/notion_add_project_fields.py <TOKEN> <DATABASE_ID>

Idempotent: existing properties with the same name are skipped.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

FIRE_CLASSES = [
    "Ф1.1", "Ф1.2", "Ф1.3", "Ф1.4",
    "Ф2.1", "Ф2.2",
    "Ф3.1", "Ф3.2", "Ф3.3", "Ф3.4", "Ф3.5", "Ф3.6",
    "Ф4.1", "Ф4.2", "Ф4.3", "Ф4.4",
    "Ф5.1", "Ф5.2", "Ф5.3",
]

# Actual property names in the DB (verified via GET):
#   1-Начало          (date)  — start
#   6-45й Заключение  (date)  — conclusion
#   3-Ответ           (date)  — answer
#   Status            (status) — workflow status
#
# Formula expressions — guarded against empty dates
DAYS_TO_ANSWER = (
    'if(empty(prop("3-Ответ")), toNumber(""), '
    'dateBetween(prop("3-Ответ"), now(), "days"))'
)
EXPERTISE_DURATION = (
    'if(empty(prop("6-45й Заключение")) or empty(prop("1-Начало")), '
    'toNumber(""), '
    'dateBetween(prop("6-45й Заключение"), prop("1-Начало"), "days"))'
)
OVERDUE = (
    'not empty(prop("3-Ответ")) '
    'and prop("3-Ответ") < now() '
    'and prop("Status") != "Положительно"'
)

NEW_PROPS = {
    "Ссылка на папку Google Drive": {"url": {}},
    "Класс объекта по МОПБ": {
        "select": {"options": [{"name": c} for c in FIRE_CLASSES]}
    },
    "Дней до ответа": {"formula": {"expression": DAYS_TO_ANSWER}},
    "Срок экспертизы, дней": {"formula": {"expression": EXPERTISE_DURATION}},
    "Просрочен?": {"formula": {"expression": OVERDUE}},
    "Замечания по проектам": {"url": {}},
}


def api_call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API {e.code}: {detail}") from None


def main() -> int:
    token = os.environ.get("NOTION_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
    db_id = os.environ.get("NOTION_DATABASE_ID") or (sys.argv[2] if len(sys.argv) > 2 else "")

    if not token or not db_id:
        print("ERROR: need NOTION_TOKEN and NOTION_DATABASE_ID (env or argv)")
        print("Usage: python notion_add_project_fields.py <TOKEN> <DATABASE_ID>")
        return 2

    print(f"→ Fetching database {db_id[:8]}…")
    db = api_call("GET", f"/databases/{db_id}", token)
    existing = set(db.get("properties", {}).keys())
    title = db.get("title", [{}])[0].get("plain_text", "(no title)")
    print(f"  Database: «{title}»")
    print(f"  Existing properties: {len(existing)}")

    to_add = {name: spec for name, spec in NEW_PROPS.items() if name not in existing}
    skipped = [name for name in NEW_PROPS if name in existing]

    if skipped:
        print(f"  Skipping (already exist): {', '.join(skipped)}")
    if not to_add:
        print("✔ Nothing to add — all 6 fields already present.")
        return 0

    print(f"→ Adding {len(to_add)} properties: {', '.join(to_add.keys())}")
    result = api_call("PATCH", f"/databases/{db_id}", token, {"properties": to_add})

    added = [p for p in to_add if p in result.get("properties", {})]
    print(f"✔ Added {len(added)}/{len(to_add)} properties")
    for p in added:
        kind = next(iter(result["properties"][p].keys() - {"id", "name", "type"}), "?")
        print(f"    • {p}  →  {result['properties'][p].get('type', kind)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
