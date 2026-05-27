"""Replace 'Срок экспертизы, дней' formula with working-days calculation.

Working days = total_days - weekends - RK_2026_holidays_in_range.

RK holidays that fall on weekdays in 2026 (14 dates):
  01.01, 02.01, 07.01, 09.03, 23.03, 24.03, 25.03,
  01.05, 07.05, 11.05, 27.05, 06.07, 26.10, 16.12

Formula assumes both endpoints inclusive.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.request

RK_HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-02", "2026-01-07",
    "2026-03-09", "2026-03-23", "2026-03-24", "2026-03-25",
    "2026-05-01", "2026-05-07", "2026-05-11", "2026-05-27",
    "2026-07-06", "2026-10-26", "2026-12-16",
]

START = 'prop("1-Начало")'
END = 'prop("6-45й Заключение")'


def to_ms(iso_date: str) -> int:
    """Convert YYYY-MM-DD to Unix timestamp in ms (UTC midnight)."""
    d = dt.datetime.fromisoformat(iso_date).replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def holiday_check(iso_date: str) -> str:
    # parseDate() returns a date whose type cannot be compared with a property
    # date (Notion raises "Type error"). fromTimestamp(ms) returns a compatible
    # date — so all holidays are encoded as Unix ms.
    d = f'fromTimestamp({to_ms(iso_date)})'
    return (
        f'if(dateBetween({d}, {START}, "days") >= 0 '
        f'and dateBetween({END}, {d}, "days") >= 0, 1, 0)'
    )


def build_formula() -> str:
    # Inline expressions only. let() cannot bind dateBetween results in this
    # Notion formula runtime — it raises a type error. So compute each piece
    # inline from START/END rather than caching in a variable.
    total = f'(dateBetween({END}, {START}, "days") + 1)'
    dow = f'day({START})'
    w = f'floor({total} / 7)'
    r = f'({total} - 7 * {w})'
    sun = f'if((7 - {dow}) % 7 < {r}, 1, 0)'
    sat = f'if((13 - {dow}) % 7 < {r}, 1, 0)'
    holidays = " + ".join(holiday_check(d) for d in RK_HOLIDAYS_2026)

    core = f'{total} - 2 * {w} - {sun} - {sat} - ({holidays})'
    formula = f'if(empty({START}) or empty({END}), toNumber(""), {core})'

    assert formula.count("(") == formula.count(")"), (
        f"unbalanced parens: open={formula.count('(')}, close={formula.count(')')}"
    )
    return formula


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


def load_env():
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

    formula = build_formula()
    print(f"→ Formula length: {len(formula)} chars")
    print(f"→ Holidays encoded: {len(RK_HOLIDAYS_2026)}")

    # In API 2025-09-03 databases contain one or more data_sources; properties
    # live on data_sources. Resolve first.
    db = api_call("GET", f"/databases/{db_id}", token)
    ds_id = db["data_sources"][0]["id"]
    print(f"→ data_source: {ds_id}")

    body = {
        "properties": {
            "Срок экспертизы, дней": {"formula": {"expression": formula}}
        }
    }
    result = api_call("PATCH", f"/data_sources/{ds_id}", token, body)
    prop = result.get("properties", {}).get("Срок экспертизы, дней", {})
    expr = prop.get("formula", {}).get("expression", "")
    print(f"✔ Patched. Stored expression length: {len(expr)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
