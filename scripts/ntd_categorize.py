"""Раскладывает файлы из Desktop/НТД по папкам согласно АГСК-1 2025.xlsx.

Логика:
  1. Парсим xlsx: определяем КОМПЛЕКСы и список их документов.
  2. Для каждого документа вытаскиваем "числовую сигнатуру" (например,
     "СП РК 2.02-101-2022" → "2.02-101-2022") — это ключ сопоставления.
  3. Для каждого файла в Desktop/НТД берём ту же сигнатуру из имени.
  4. Совпадения → перемещаем в папку с именем КОМПЛЕКСа.
  5. Неподошедшие → _UNMATCHED/.
  6. Документы из xlsx без файла → отдельный отчёт.

По умолчанию --dry-run: показывает план без перемещения.
Флаг --apply — реально двигает файлы.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import openpyxl

GDRIVE_ROOT = pathlib.Path(os.getenv("GDRIVE_ROOT", str(pathlib.Path.home() / "GoogleDrive" / "Мой диск")))

NTD_DIR = Path.home() / "Desktop" / "НТД"
XLSX = GDRIVE_ROOT / "НТД" / "АГСК-1" / "АГСК-1 2025.xlsx"
UNMATCHED_DIR = "_UNMATCHED"


# ---- извлечение сигнатуры ----

SIG_RE = re.compile(r"\d[\d.\-\u2013\u2014]*")


def signature(raw: str) -> str | None:
    """Числовая сигнатура: самая длинная подстрока из цифр/точек/дефисов.

    Примеры:
      'СП РК 2.02-101-2022' → '2.02-101-2022'
      'SP-RK-2.02-101-2022' → '2.02-101-2022'
      'СН 387-78'          → '387-78'
      'МСН 10-01-2012'     → '10-01-2012'
    """
    if not raw:
        return None
    s = raw.replace("–", "-").replace("—", "-")
    cands = SIG_RE.findall(s)
    if not cands:
        return None
    # самая длинная подстрока — обычно сама сигнатура
    best = max(cands, key=len)
    # нормализуем
    best = best.strip(".-")
    # сигнатура должна иметь хотя бы один дефис ИЛИ быть формата X.XX-...
    if "-" not in best and "." not in best:
        return None
    # должна содержать минимум 4 символа
    if len(best) < 4:
        return None
    return best


# ---- парсинг xlsx ----

# строки, которые являются не документами, а подзаголовками
SUBHEADER_KEYS = {
    "закон", "правила", "перечень", "методические указания",
    "правила и разрешительные требования",
    "нормативные технические документы, устанавливающие обязательные требования",
    "нормативные технические документы добровольного применения",
    "производные нормативные правовые акты",
    "методические рекомендации",
    "кодекс",
    "инструкция",
}

KOMPLEX_RE = re.compile(r"^\s*КОМПЛЕКС\s+[\d.]+", re.IGNORECASE)


def parse_xlsx(path: Path) -> tuple[list[tuple[str, list[dict]]], dict]:
    """Возвращает (komplex_list, info).

    komplex_list: [(komplex_name, [{'code': ..., 'title': ..., 'sig': ...}, ...])]
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active

    groups: list[tuple[str, list[dict]]] = []
    current: tuple[str, list[dict]] | None = None
    stats = {"total_rows": 0, "doc_rows": 0, "subheader_rows": 0, "komplex_rows": 0}

    for row in ws.iter_rows(values_only=True):
        stats["total_rows"] += 1
        col_a = (row[0] or "").strip() if row and row[0] else ""
        col_b = (row[1] or "").strip() if row and len(row) > 1 and row[1] else ""
        if not col_a and not col_b:
            continue

        if KOMPLEX_RE.match(col_a):
            stats["komplex_rows"] += 1
            # чистим \xa0 и хвосты
            name = re.sub(r"\s+", " ", col_a).strip()
            current = (name, [])
            groups.append(current)
            continue

        # Пропускаем подзаголовки (строки без col_b и с "тематическим" col_a)
        col_a_lower = col_a.lower().strip(" .")
        if not col_b and col_a_lower in SUBHEADER_KEYS:
            stats["subheader_rows"] += 1
            continue
        # Документы без кода (типа "Закон", "Правила") — пропускаем,
        # они не имеют сигнатуры и плохо матчатся
        if col_a_lower in SUBHEADER_KEYS:
            stats["subheader_rows"] += 1
            continue

        # Это документ
        stats["doc_rows"] += 1
        if current is None:
            # документ до первого КОМПЛЕКСа — кладём в виртуальный
            current = ("КОМПЛЕКС 0.00 Без категории", [])
            groups.append(current)
        sig = signature(col_a)
        current[1].append({"code": col_a, "title": col_b, "sig": sig})

    return groups, stats


def sanitize_folder(name: str) -> str:
    """КОМПЛЕКС-имя → безопасное имя папки (сохраняем кириллицу, убираем
    недопустимые символы Windows).
    """
    # Windows запрещает: < > : " / \ | ? *
    s = re.sub(r"[<>:\"/\\|?*]", "", name)
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    # максимальная длина — 120, чтобы уместиться в лимит пути
    return s[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Реально перемещать файлы (по умолчанию — dry-run)")
    ap.add_argument("--report", type=Path,
                    default=Path("rezult/ntd_categorize_report.txt"),
                    help="Куда писать отчёт")
    args = ap.parse_args()

    if not NTD_DIR.exists():
        print(f"ERR: {NTD_DIR} не найдена")
        return 2
    if not XLSX.exists():
        print(f"ERR: {XLSX} не найден")
        return 2

    # Файлы в НТД
    files = sorted(NTD_DIR.glob("*.md"))
    # сигнатура → список файлов (может быть несколько)
    files_by_sig: dict[str, list[Path]] = defaultdict(list)
    files_no_sig: list[Path] = []
    for f in files:
        sig = signature(f.stem)
        if sig:
            files_by_sig[sig].append(f)
        else:
            files_no_sig.append(f)

    # Парсим xlsx
    groups, xlsx_stats = parse_xlsx(XLSX)
    print(f"XLSX: {xlsx_stats}")
    print(f"КОМПЛЕКСов:  {len(groups)}")
    print(f"Файлов в НТД: {len(files)}")
    print(f"С сигнатурой: {len(files) - len(files_no_sig)}")
    print(f"Без сигнатуры: {len(files_no_sig)}")
    print()

    # Строим план: файл → КОМПЛЕКС
    plan: list[tuple[Path, str, dict]] = []  # (file, komplex, doc_info)
    matched_files: set[Path] = set()
    komplex_missing: dict[str, list[dict]] = defaultdict(list)

    # Индекс всех сигнатур из xlsx: sig → [(komplex, doc), ...]
    sig_to_docs: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for komplex, docs in groups:
        for d in docs:
            if d["sig"]:
                sig_to_docs[d["sig"]].append((komplex, d))

    # Сопоставляем файлы с документами из xlsx
    for sig, flist in files_by_sig.items():
        matches = sig_to_docs.get(sig, [])
        if matches:
            # используем первый матч (обычно один)
            komplex, doc = matches[0]
            for f in flist:
                plan.append((f, komplex, doc))
                matched_files.add(f)

    # Документы из xlsx, для которых файл не нашёлся
    matched_sigs = {p[2]["sig"] for p in plan if p[2]["sig"]}
    for komplex, docs in groups:
        for d in docs:
            if d["sig"] and d["sig"] not in files_by_sig:
                komplex_missing[komplex].append(d)

    # Неопределённые файлы (сигнатура не нашлась)
    unmatched = [f for f in files if f not in matched_files]

    # === Отчёт ===
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("ПЛАН КАТЕГОРИЗАЦИИ")
    lines.append("=" * 72)
    lines.append(f"Файлов всего:       {len(files)}")
    lines.append(f"Будет разложено:    {len(plan)}")
    lines.append(f"В _UNMATCHED:       {len(unmatched)}")
    lines.append("")

    # Раскладка по КОМПЛЕКСам
    by_komplex: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for f, k, d in plan:
        by_komplex[k].append((f, d))

    lines.append(f"КОМПЛЕКСов с файлами: {len(by_komplex)}")
    lines.append("")
    for komplex in sorted(by_komplex.keys()):
        items = by_komplex[komplex]
        lines.append(f"\n[{len(items)}] {komplex}")
        for f, d in sorted(items, key=lambda x: x[0].name):
            lines.append(f"    {f.name}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("UNMATCHED (в папку _UNMATCHED)")
    lines.append("=" * 72)
    for f in unmatched:
        lines.append(f"  {f.name}  sig={signature(f.stem)}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("ДОКУМЕНТЫ ИЗ XLSX БЕЗ ФАЙЛА (топ-20 КОМПЛЕКСов)")
    lines.append("=" * 72)
    for i, (komplex, missing) in enumerate(
        sorted(komplex_missing.items(), key=lambda x: -len(x[1]))
    ):
        if i >= 20:
            break
        lines.append(f"\n[{len(missing)}] {komplex}")
        for d in missing[:10]:
            lines.append(f"    {d['code']}  —  {d['title'][:80]}")
        if len(missing) > 10:
            lines.append(f"    ... ещё {len(missing) - 10}")

    report_text = "\n".join(lines)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text, encoding="utf-8")
    print(f"Отчёт: {args.report}")

    # Короткая сводка в stdout
    print()
    print(f"Будет разложено по {len(by_komplex)} КОМПЛЕКСам:")
    for komplex in sorted(by_komplex.keys())[:30]:
        print(f"  [{len(by_komplex[komplex]):3d}] {komplex[:90]}")
    if len(by_komplex) > 30:
        print(f"  ... ещё {len(by_komplex) - 30}")
    print()
    print(f"В _UNMATCHED: {len(unmatched)}")

    # === Применение ===
    if not args.apply:
        print("\n[dry-run] Файлы НЕ перемещены. Добавь --apply чтобы применить.")
        return 0

    print("\nПрименяю перемещения...")
    moved = 0
    errors: list[str] = []

    # сначала создаём папки
    for komplex in by_komplex:
        (NTD_DIR / sanitize_folder(komplex)).mkdir(exist_ok=True)
    if unmatched:
        (NTD_DIR / UNMATCHED_DIR).mkdir(exist_ok=True)

    # перемещаем
    for f, komplex, _d in plan:
        dst = NTD_DIR / sanitize_folder(komplex) / f.name
        try:
            shutil.move(str(f), str(dst))
            moved += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {e}")

    for f in unmatched:
        dst = NTD_DIR / UNMATCHED_DIR / f.name
        try:
            shutil.move(str(f), str(dst))
            moved += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {e}")

    print(f"Перемещено: {moved} / {len(files)}")
    if errors:
        print(f"Ошибки: {len(errors)}")
        for e in errors[:10]:
            print(f"  {e}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
