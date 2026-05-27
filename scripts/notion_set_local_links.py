"""Populate 'Ссылка на папку Google Drive' and 'Замечания по проектам'
with file:// links to $PROJECTS_ROOT/<project folder>.

Folder naming is inconsistent (`01-03_00289_Гибридная_элстан_4B` with
underscores, `01-03_17452 СППД Кариман` with spaces, etc.), so the match
key is the `01-03_NNNNN` prefix derived from Notion's `Номер` field.

The comments file is looked up by substring «замечан» (case-insensitive)
with extension .xlsx / .xls / .docx / .doc.

Usage:
    python scripts/notion_set_local_links.py            # dry-run (default)
    python scripts/notion_set_local_links.py --apply    # actually PATCH

Safety: dry-run prints planned changes. Pass --apply to execute.
Existing non-empty values are overwritten (user asked to re-point Google
Drive URLs to local paths). Pass --skip-existing to preserve them.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOTS = [
    pathlib.Path(os.getenv("PROJECTS_ROOT", str(pathlib.Path.home() / "ПРОЕКТЫ"))),
    pathlib.Path(os.getenv("GDRIVE_ROOT", str(pathlib.Path.home() / "GoogleDrive" / "Мой диск"))) / "ГосЭкспертиза" / "Project",
]
FOLDER_PROP = "Ссылка на папку"
COMMENTS_PROP = "Замечания по проектам"
TITLE_PROP = "Номер"

PREFIX_RE = re.compile(r"^(\d{2}-\d{2}_\d{4,6})")
COMMENTS_RE = re.compile(r"замечан", re.IGNORECASE)
COMMENTS_EXTS = (".xlsx", ".xls", ".docx", ".doc")


def load_env() -> None:
    p = pathlib.Path(__file__).resolve().parent.parent / ".env"
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


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
        raise RuntimeError(f"Notion API {e.code} {method} {path}: {detail}") from None


def scan_folders(roots: list[pathlib.Path]) -> dict[str, pathlib.Path]:
    """Return {prefix: folder_path} scanning all roots. Earlier roots win on collision."""
    out: dict[str, pathlib.Path] = {}
    collisions: dict[str, list[str]] = {}
    for root in roots:
        if not root.exists():
            print(f"  [skip] root does not exist: {root}")
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            m = PREFIX_RE.match(child.name)
            if not m:
                continue
            prefix = m.group(1)
            if prefix in out:
                collisions.setdefault(prefix, [str(out[prefix])]).append(str(child))
            else:
                out[prefix] = child
    for prefix, paths in collisions.items():
        print(f"  [warn] prefix {prefix} matches multiple folders: {paths} — using {out[prefix]}")
    return out


def find_comments_file(folder: pathlib.Path) -> pathlib.Path | None:
    for f in folder.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in COMMENTS_EXTS:
            continue
        if COMMENTS_RE.search(f.name):
            return f
    return None


LOCAL_SERVER = "http://127.0.0.1:17234/open"  # scripts/openp_server.py


def to_file_uri(path: pathlib.Path, is_dir: bool) -> str:
    # Windows path → http://127.0.0.1:17234/open?p=<url-encoded path>
    # Browsers / Notion block file:// and unknown custom schemes, so we route
    # through a loopback HTTP server which validates the path is inside
    # $PROJECTS_ROOT and calls subprocess.run(["open", ...]).
    p = str(path).replace("\\", "/")
    if is_dir and not p.endswith("/"):
        p += "/"
    # Full encode for query-string value — no `safe` chars kept unescaped.
    encoded = urllib.parse.quote(p, safe="")
    return f"{LOCAL_SERVER}?p={encoded}"


def query_all_pages(token: str, ds_id: str) -> list[dict]:
    """Paginate through all rows in the data source."""
    pages: list[dict] = []
    cursor = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = api_call("POST", f"/data_sources/{ds_id}/query", token, body)
        pages.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return pages


def get_title(page: dict) -> str:
    prop = page["properties"].get(TITLE_PROP, {})
    if prop.get("type") != "title":
        return ""
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()


def get_url(page: dict, name: str) -> str | None:
    prop = page["properties"].get(name, {})
    if prop.get("type") != "url":
        return None
    return prop.get("url")


def normalize_to_prefix(title: str) -> str | None:
    """Notion title `01-03/00289` → disk prefix `01-03_00289`."""
    t = title.strip().replace("/", "_").replace("\\", "_")
    m = PREFIX_RE.match(t)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually PATCH pages (default: dry-run)")
    ap.add_argument("--skip-existing", action="store_true", help="don't overwrite non-empty URL values")
    args = ap.parse_args()

    load_env()
    token = os.environ["NOTION_TOKEN"]
    db_id = os.environ["NOTION_DATABASE_ID"]

    print(f"→ Scanning roots:")
    for r in ROOTS:
        print(f"    {r}")
    folder_map = scan_folders(ROOTS)
    print(f"  found {len(folder_map)} matching folders")

    print(f"→ Notion DB {db_id[:8]}…")
    db = api_call("GET", f"/databases/{db_id}", token)
    ds_id = db["data_sources"][0]["id"]
    pages = query_all_pages(token, ds_id)
    print(f"  {len(pages)} rows")

    planned: list[tuple[dict, dict]] = []  # (page, properties_patch)
    unmatched: list[str] = []
    no_comments: list[str] = []

    for page in pages:
        title = get_title(page)
        prefix = normalize_to_prefix(title)
        if not prefix:
            unmatched.append(f"[no prefix] {title!r}")
            continue
        folder = folder_map.get(prefix)
        if not folder:
            unmatched.append(f"[no folder] {title} → {prefix}")
            continue

        patch: dict = {}

        folder_uri = to_file_uri(folder, is_dir=True)
        cur_folder = get_url(page, FOLDER_PROP)
        if args.skip_existing and cur_folder:
            pass
        elif cur_folder != folder_uri:
            patch[FOLDER_PROP] = {"url": folder_uri}

        comments_file = find_comments_file(folder)
        if comments_file:
            file_uri = to_file_uri(comments_file, is_dir=False)
            cur_comments = get_url(page, COMMENTS_PROP)
            if args.skip_existing and cur_comments:
                pass
            elif cur_comments != file_uri:
                patch[COMMENTS_PROP] = {"url": file_uri}
        else:
            no_comments.append(f"{title} → {folder.name}")

        if patch:
            planned.append((page, patch))

    # Report
    print()
    print(f"→ Plan: {len(planned)} rows to update")
    for page, patch in planned[:20]:
        title = get_title(page)
        print(f"  • {title}")
        for k, v in patch.items():
            print(f"      {k}: {v['url']}")
    if len(planned) > 20:
        print(f"  … and {len(planned) - 20} more")

    if unmatched:
        print(f"\n→ {len(unmatched)} rows without a matching folder:")
        for line in unmatched[:20]:
            print(f"  - {line}")
        if len(unmatched) > 20:
            print(f"  … and {len(unmatched) - 20} more")

    if no_comments:
        print(f"\n→ {len(no_comments)} folders without a comments file (folder link only):")
        for line in no_comments[:20]:
            print(f"  - {line}")
        if len(no_comments) > 20:
            print(f"  … and {len(no_comments) - 20} more")

    if not args.apply:
        print("\n[dry-run] Pass --apply to execute.")
        return 0

    print(f"\n→ Applying {len(planned)} updates…")
    ok = 0
    errors: list[str] = []
    for page, patch in planned:
        try:
            api_call("PATCH", f"/pages/{page['id']}", token, {"properties": patch})
            ok += 1
        except RuntimeError as e:
            errors.append(f"{get_title(page)}: {e}")

    print(f"✔ Updated {ok}/{len(planned)}")
    if errors:
        print(f"✗ {len(errors)} failed:")
        for e in errors[:10]:
            print(f"  - {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
