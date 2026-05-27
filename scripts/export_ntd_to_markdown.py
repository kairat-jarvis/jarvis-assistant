"""Экспорт базы НТД из Supabase в локальные .md-файлы.

Назначение: вытащить 395 документов + ~90k пунктов из таблиц `ntd_documents`
и `clause_vectors` в плоский .md-архив для офлайн-режима пилота РГП
(Claude Desktop Knowledge, mopb-agent, локальная экспертиза без Supabase).

Структура вывода:
    load/ntd_export/
        OVIK/<doc_code>.md     — отопление, вентиляция, кондиционирование, тепло
        KR/<doc_code>.md       — конструктивные решения, грунты, фундаменты, бетон
        MOPB/<doc_code>.md     — пожарная безопасность, СОУЭ, АПС, эвакуация
        General/<doc_code>.md  — общие, не отнесённые к разделам
        _index.md              — оглавление по всем документам с метаданными

Каждый .md-файл содержит:
    # <doc_code>
    > doc_type · doc_year · doc_status
    ## <section_path>
    <content пункта>
    ...

Сортировка пунктов: по `section_path` (естественная сортировка по уровням).

Использование:
    cp .env.example .env  # выставить SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
    python scripts/export_ntd_to_markdown.py --out load/ntd_export
    python scripts/export_ntd_to_markdown.py --out load/ntd_export --only "СП РК 2.02"
    python scripts/export_ntd_to_markdown.py --out load/ntd_export --dry-run

Запросы к Supabase: PostgREST через urllib (без сторонних зависимостей).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "load" / "ntd_export"

PAGE_SIZE = 1000  # PostgREST default cap; используем Range-заголовок


# --- классификация документов по разделам экспертизы ---
#
# В нашей базе doc_title == doc_code для большинства записей, поэтому
# классификация делается в первую очередь по структуре кода СН/СП РК:
#
#   2.02 — пожарная безопасность зданий/сооружений   → MOPB
#   2.03 — сейсмостойкое строительство                → KR
#   3.02 — здания и сооружения (несущие конструкции)  → KR
#   3.03 — мосты, тоннели, гидротехника               → KR
#   4.01 — отопление, вентиляция, теплоснабжение      → OVIK
#   4.02 — водоснабжение и канализация (ВК)           → General (не ОВИК)
#   4.04 — связь                                       → General
#
# Если кода в правилах нет — ищем ключевые слова в коде/title (например,
# для ВСН/ВНТП/Приказов нет регулярной нумерации).

CODE_PREFIX_RULES: list[tuple[str, str]] = [
    (r"\bСН РК\s*2\.02-", "MOPB"),
    (r"\bСН РК\s*2\.03-", "KR"),
    (r"\bСН РК\s*3\.02-", "KR"),
    (r"\bСН РК\s*3\.03-", "KR"),
    (r"\bСН РК\s*4\.01-", "OVIK"),
    (r"\bС[ПHН]иП РК\s*3\.02-", "KR"),
    (r"\bС[ПHН]иП РК\s*3\.03-", "KR"),
    (r"\bС[ПHН]иП РК\s*4\.01-", "OVIK"),
    (r"\bСП РК\s*2\.02-", "MOPB"),
    (r"\bСП РК\s*2\.04-", "OVIK"),       # 2.04 — климат/теплотехника зданий
    (r"\bСП РК\s*3\.02-", "KR"),
    (r"\bСП РК\s*3\.03-", "KR"),
    (r"\bСП РК\s*4\.01-", "OVIK"),
    (r"\bС[ПHН]иП\s*2\.04\.", "OVIK"),
    (r"\bС[ПHН]иП\s*2\.08\.", "KR"),
    (r"\bМСН\s*4\.02-", "OVIK"),         # МСН 4.02 — отопление, вентиляция (исторически)
    (r"\bМСН\s*2\.02-", "MOPB"),
    (r"\bМСН\s*3\.02-", "KR"),
    (r"\bРДС РК\s*3\.02-", "KR"),
    (r"\bРДС РК\s*3\.01-", "MOPB"),       # 3.01 — пожарные нормы исторически
    (r"\bСН РК EN 1991-1-2", "MOPB"),     # Еврокоды огнестойкости
    (r"\bСН РК EN 199[2-6]-1-2", "MOPB"),
]

KEYWORD_RULES: list[tuple[str, list[str]]] = [
    (
        "MOPB",
        [
            "пожар", "огнестой", "огнезащит", "противопожар", "соуэ", "апс",
            "эваку", "взрыв", "горюч",
        ],
    ),
    (
        "OVIK",
        [
            "отоплен", "вентиляц", "кондицион", "теплоснабжен", "теплосет",
            "котельн", "газоснабжен", "холодоснабжен", "тепловой пункт",
            "тепловая защита",
        ],
    ),
    (
        "KR",
        [
            "конструктивн", "фундамент", "основани", "грунт", "железобетон",
            "металлоконструк", "несущ.*конструк", "сейсмостой", "кладк",
        ],
    ),
]

SECTION_FALLBACK = "General"
KNOWN_SECTIONS = ("OVIK", "KR", "MOPB", SECTION_FALLBACK)


def classify(doc_code: str, doc_title: str | None) -> str:
    for pat, section in CODE_PREFIX_RULES:
        if re.search(pat, doc_code, flags=re.IGNORECASE):
            return section
    haystack = f"{doc_code} {doc_title or ''}".lower()
    for section, patterns in KEYWORD_RULES:
        for pat in patterns:
            if re.search(pat, haystack):
                return section
    return SECTION_FALLBACK


# --- сортировка section_path вида "7 > 5 > 6" ---

_NUM_RE = re.compile(r"\d+")


def section_key(path: str | None) -> tuple:
    if not path:
        return ()
    parts: list[int] = []
    for token in path.replace(">", " ").replace(".", " ").split():
        nums = _NUM_RE.findall(token)
        if nums:
            parts.append(int(nums[0]))
    return tuple(parts)


# --- PostgREST клиент ---


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept-Profile": "public",
            "Content-Type": "application/json",
        }

    def _request(self, path: str, params: dict, *, range_header: str | None = None) -> list[dict]:
        qs = urllib.parse.urlencode(params, doseq=True, safe="(),:.*")
        req = urllib.request.Request(f"{self.base}/{path}?{qs}", headers=dict(self.headers))
        if range_header:
            req.add_header("Range-Unit", "items")
            req.add_header("Range", range_header)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"PostgREST {exc.code} on {path}: {body}") from exc

    def select(self, table: str, *, columns: str, filters: dict | None = None,
               order: str | None = None) -> list[dict]:
        """Постраничный select. Возвращает все строки целиком."""
        all_rows: list[dict] = []
        offset = 0
        while True:
            params: dict = {"select": columns}
            if filters:
                params.update(filters)
            if order:
                params["order"] = order
            rng = f"{offset}-{offset + PAGE_SIZE - 1}"
            chunk = self._request(table, params, range_header=rng)
            if not chunk:
                break
            all_rows.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return all_rows


# --- рендеринг ---


def render_doc(doc: dict, clauses: list[dict]) -> str:
    code = doc["doc_code"]
    title = doc.get("doc_title") or code
    meta_bits = []
    if doc.get("doc_type"):
        meta_bits.append(doc["doc_type"])
    if doc.get("doc_year"):
        meta_bits.append(str(doc["doc_year"]))
    if doc.get("doc_status"):
        meta_bits.append(doc["doc_status"])
    if doc.get("superseded_by"):
        meta_bits.append(f"заменён: {doc['superseded_by']}")

    out: list[str] = []
    out.append(f"# {code}")
    if title != code:
        out.append(f"## {title}")
    if meta_bits:
        out.append(f"> {' · '.join(meta_bits)}")
    out.append("")

    # пункты — упорядочены по section_path
    sorted_clauses = sorted(
        clauses,
        key=lambda c: section_key((c.get("metadata") or {}).get("section_path")),
    )
    for c in sorted_clauses:
        meta = c.get("metadata") or {}
        clause_no = meta.get("clause_no") or meta.get("section_path") or ""
        heading = clause_no.lstrip("p.").strip() if clause_no else ""
        if heading:
            out.append(f"### {heading}")
        body = (c.get("content") or "").strip()
        if body:
            out.append(body)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def render_index(sections: dict[str, list[dict]]) -> str:
    lines = ["# Архив НТД — оглавление", ""]
    lines.append(f"Всего документов: {sum(len(v) for v in sections.values())}")
    lines.append("")
    for section in KNOWN_SECTIONS:
        docs = sections.get(section, [])
        if not docs:
            continue
        lines.append(f"## {section} ({len(docs)})")
        lines.append("")
        for d in sorted(docs, key=lambda x: x["doc_code"]):
            year = f" · {d['doc_year']}" if d.get("doc_year") else ""
            status = f" · {d['doc_status']}" if d.get("doc_status") and d["doc_status"] != "active" else ""
            lines.append(f"- [{d['doc_code']}]({section}/{safe_filename(d['doc_code'])}.md){year}{status}")
        lines.append("")
    return "\n".join(lines)


# --- утилиты ---


_BAD_CHARS_RE = re.compile(r"[^\w\-\.Ѐ-ӿ]+", re.UNICODE)


def safe_filename(code: str) -> str:
    name = _BAD_CHARS_RE.sub("_", code).strip("_")
    return name or "unnamed"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


# --- main ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"Куда писать .md (по умолчанию {DEFAULT_OUT})")
    parser.add_argument("--only", type=str, default=None,
                        help="ILIKE-маска по doc_code (например, 'СП РК 2.02')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать план, файлы не писать")
    args = parser.parse_args(argv)

    load_env(REPO_ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.stderr.write(
            "Нужны переменные SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY в .env\n"
            "(SERVICE_ROLE — потому что нам нужен полный доступ на чтение).\n"
        )
        return 2

    client = SupabaseClient(url, key)

    print("Загружаю список документов…", flush=True)
    doc_filters: dict = {}
    if args.only:
        doc_filters["doc_code"] = f"ilike.*{args.only}*"
    docs = client.select(
        "ntd_documents",
        columns="id,doc_code,doc_title,doc_type,doc_year,doc_status,superseded_by",
        filters=doc_filters,
        order="doc_code.asc",
    )
    print(f"  → {len(docs)} документов", flush=True)

    sections: dict[str, list[dict]] = defaultdict(list)
    written = 0
    skipped = 0

    for i, doc in enumerate(docs, 1):
        code = doc["doc_code"]
        section = classify(code, doc.get("doc_title"))
        sections[section].append(doc)

        print(f"[{i:>3}/{len(docs)}] {section}/{code}", end=" ", flush=True)
        clauses = client.select(
            "clause_vectors",
            columns="content,metadata",
            filters={"document_id": f"eq.{doc['id']}"},
        )
        print(f"({len(clauses)} clauses)", flush=True)

        if not clauses:
            skipped += 1
            continue

        if args.dry_run:
            written += 1
            continue

        section_dir = args.out / section
        section_dir.mkdir(parents=True, exist_ok=True)
        target = section_dir / f"{safe_filename(code)}.md"
        target.write_text(render_doc(doc, clauses), encoding="utf-8")
        written += 1

    if not args.dry_run and docs:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "_index.md").write_text(render_index(sections), encoding="utf-8")

    print("")
    print(f"Готово. Записано: {written}, пропущено (без пунктов): {skipped}")
    for section in KNOWN_SECTIONS:
        n = len(sections.get(section, []))
        if n:
            print(f"  {section}: {n}")
    if args.dry_run:
        print("(dry-run — файлы не записаны)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
