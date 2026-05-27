"""Inspect one page's actual property keys + data_source schema property IDs."""
from __future__ import annotations
import json
import os
import pathlib
import urllib.request


def load_env() -> None:
    p = pathlib.Path(__file__).resolve().parent.parent / ".env"
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


def api(method: str, path: str, body=None) -> dict:
    url = f"https://api.notion.com/v1{path}"
    headers = {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    load_env()
    db_id = os.environ["NOTION_DATABASE_ID"]

    db = api("GET", f"/databases/{db_id}")
    ds_id = db["data_sources"][0]["id"]
    print(f"data_source: {ds_id}")

    ds = api("GET", f"/data_sources/{ds_id}")
    print("\n=== data_source.properties (schema) ===")
    for name, spec in ds.get("properties", {}).items():
        if "ссылк" in name.lower() or "замечан" in name.lower() or name == "Номер":
            print(f"  {name!r}  id={spec.get('id')!r}  type={spec.get('type')}")

    rows = api("POST", f"/data_sources/{ds_id}/query", {"page_size": 1})
    page = rows["results"][0]
    print(f"\n=== sample page {page['id']} .properties keys ===")
    for name, val in page["properties"].items():
        print(f"  {name!r}  id={val.get('id')!r}  type={val.get('type')}")


if __name__ == "__main__":
    main()
