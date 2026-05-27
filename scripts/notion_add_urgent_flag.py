"""Add '🔴 Срочно' formula property to 'Проекты Экспертиза'.

Shows "🔴" when 'Дней до ответа' is 0 or 1 (answer deadline is today or
tomorrow, not yet overdue). Empty otherwise.

API note: style() cannot be used conditionally over prop() values (Notion
raises 'Type error with formula'), so the red highlight is rendered via the
🔴 emoji rather than style(text, "b", "red"). See .claude/skills/notion
§"style() gotcha" for details.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

PROP_NAME = "🔴 Срочно"
ANSWER_DATE = 'prop("3-Ответ")'
DAYS = f'dateBetween({ANSWER_DATE}, now(), "days")'

FORMULA = (
    f'if(empty({ANSWER_DATE}), "", '
    f'if({DAYS} >= 0 and {DAYS} <= 1, "🔴", ""))'
)


def api_call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"https://api.notion.com/v1{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2025-09-03",
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


def load_env() -> None:
    p = pathlib.Path(__file__).resolve().parent.parent / ".env"
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


def main() -> int:
    load_env()
    token = os.environ["NOTION_TOKEN"]
    db_id = os.environ["NOTION_DATABASE_ID"]

    print(f"→ Formula: {FORMULA}")

    db = api_call("GET", f"/databases/{db_id}", token)
    ds_id = db["data_sources"][0]["id"]
    print(f"→ data_source: {ds_id}")

    body = {"properties": {PROP_NAME: {"formula": {"expression": FORMULA}}}}
    result = api_call("PATCH", f"/data_sources/{ds_id}", token, body)

    prop = result.get("properties", {}).get(PROP_NAME, {})
    expr = prop.get("formula", {}).get("expression", "")
    ptype = prop.get("type", "?")
    print(f"✔ Patched «{PROP_NAME}» → type={ptype}, stored={len(expr)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
