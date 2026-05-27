"""Нормализация папки НТД: перезапись исходников + переименование.

Что делает:
  1. Для каждого .md:
     - убирает URL-encoded мусор в ссылках оглавления
     - убирает Word-закладки `%22 %5Cl %22sub...`
     - NBSP (\u00a0) → обычный пробел
     - \r\n → \n
     - табы → 4 пробела
     - схлопывает 3+ пустые строки в 2
     - убирает trailing whitespace по строкам
  2. Переименовывает файлы: кириллица → латиница, пробелы → дефисы

НЕ делает бэкап — работает деструктивно (по требованию).
НЕ трогает содержимое длинных строк (VERY_LONG_LINE) — там данные таблиц.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

NTD_DIR = Path(os.getenv("NTD_DIR", str(Path.home() / "Desktop" / "НТД")))


CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "H", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "№": "N", "«": "", "»": "", "„": "", "“": "", "”": "",
}


def transliterate(s: str) -> str:
    return "".join(CYRILLIC_MAP.get(ch, ch) for ch in s)


def safe_filename(name: str) -> str:
    """Имя файла: латиница, цифры, `-`, `_`, `.` — всё остальное → `-`."""
    stem = Path(name).stem
    ext = Path(name).suffix
    s = transliterate(stem)
    s = re.sub(r"[^\w.\-]+", "-", s, flags=re.ASCII)
    s = re.sub(r"-+", "-", s).strip("-._")
    return f"{s}{ext}" if s else f"file{ext}"


def normalize_content(text: str) -> tuple[str, dict[str, int]]:
    stats: dict[str, int] = {}

    # 1. Переносы строк — только \n
    crlf = text.count("\r\n")
    if crlf:
        text = text.replace("\r\n", "\n")
        stats["crlf→lf"] = crlf

    # 2. NBSP → пробел
    nbsp = text.count("\u00a0")
    if nbsp:
        text = text.replace("\u00a0", " ")
        stats["nbsp"] = nbsp

    # 3. Табы → 4 пробела
    tabs = text.count("\t")
    if tabs:
        text = text.replace("\t", "    ")
        stats["tabs"] = tabs

    # 4. URL-encoded "битые ссылки" вида [текст](%22...%22...)
    #    Заменяем на просто "текст" (теряем якорь, сохраняем читаемость).
    url_junk_re = re.compile(r"\[([^\]]+)\]\(%22[^)]*\)")
    cleaned, n_url = url_junk_re.subn(r"\1", text)
    if n_url:
        text = cleaned
        stats["url_junk"] = n_url

    # 5. Любые оставшиеся пустые ссылки `[text]()` → `text`
    empty_link_re = re.compile(r"\[([^\]]+)\]\(\s*\)")
    cleaned, n_empty = empty_link_re.subn(r"\1", text)
    if n_empty:
        text = cleaned
        stats["empty_links"] = n_empty

    # 6. Word-анкоры <a name="sub123"></a>
    anchor_re = re.compile(r"<a\s+name=\"[^\"]*\"\s*>\s*</a>", re.IGNORECASE)
    cleaned, n_anchors = anchor_re.subn("", text)
    if n_anchors:
        text = cleaned
        stats["word_anchors"] = n_anchors

    # 7. HTML-сущности → символы
    html_map = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&laquo;": "«",
        "&raquo;": "»",
    }
    n_html = 0
    for ent, ch in html_map.items():
        c = text.count(ent)
        if c:
            text = text.replace(ent, ch)
            n_html += c
    if n_html:
        stats["html_entities"] = n_html

    # 8. Trailing whitespace
    trimmed_lines = []
    trimmed_count = 0
    for line in text.split("\n"):
        new = line.rstrip()
        if new != line:
            trimmed_count += 1
        trimmed_lines.append(new)
    text = "\n".join(trimmed_lines)
    if trimmed_count:
        stats["trailing_ws_lines"] = trimmed_count

    # 9. Схлопываем 3+ пустых строки → 2 пустых
    collapsed, n_collapsed = re.subn(r"\n{4,}", "\n\n\n", text)
    if n_collapsed:
        text = collapsed
        stats["collapsed_blank_blocks"] = n_collapsed

    # 10. Убираем ведущие/хвостовые пустые строки у файла
    text = text.strip("\n") + "\n"

    return text, stats


def main() -> int:
    if not NTD_DIR.exists():
        print(f"ERR: папка не найдена: {NTD_DIR}")
        return 2

    files = sorted(NTD_DIR.glob("*.md"))
    if not files:
        print(f"ERR: .md-файлов не найдено в {NTD_DIR}")
        return 2

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # === Нормализация контента ===
    print(f"[1/2] Нормализация контента ({len(files)} файлов)")
    content_changed = 0
    agg_stats: dict[str, int] = {}
    errors: list[tuple[Path, str]] = []

    for f in files:
        try:
            original = f.read_text(encoding="utf-8", errors="replace")
            new_text, stats = normalize_content(original)
            if new_text != original:
                f.write_text(new_text, encoding="utf-8")
                content_changed += 1
                for k, v in stats.items():
                    agg_stats[k] = agg_stats.get(k, 0) + v
        except Exception as e:  # noqa: BLE001
            errors.append((f, str(e)))

    print(f"      Изменено файлов: {content_changed}")
    for k, v in sorted(agg_stats.items(), key=lambda x: -x[1]):
        print(f"        {k:28s} {v:,}")
    if errors:
        print(f"\n      Ошибки ({len(errors)}):")
        for f, e in errors:
            print(f"        {f.name}: {e}")

    # === Переименование ===
    print(f"\n[2/2] Переименование (кириллица/пробелы → латиница/-)")
    renamed = 0
    collisions: list[tuple[str, str]] = []
    rename_log: list[tuple[str, str]] = []
    used_names: set[str] = set()

    # Сначала формируем план, чтобы отлавливать коллизии
    plan: list[tuple[Path, Path]] = []
    for f in sorted(NTD_DIR.glob("*.md")):
        new_name = safe_filename(f.name)
        if new_name == f.name:
            used_names.add(new_name.lower())
            continue
        # коллизия с существующим именем?
        candidate = new_name
        base, ext = Path(candidate).stem, Path(candidate).suffix
        i = 2
        while (
            candidate.lower() in used_names
            or (NTD_DIR / candidate).exists() and (NTD_DIR / candidate) != f
        ):
            candidate = f"{base}-{i}{ext}"
            i += 1
            if i > 99:
                break
        used_names.add(candidate.lower())
        plan.append((f, NTD_DIR / candidate))

    for src, dst in plan:
        try:
            src.rename(dst)
            renamed += 1
            rename_log.append((src.name, dst.name))
        except OSError as e:
            collisions.append((src.name, f"{dst.name}: {e}"))

    print(f"      Переименовано: {renamed}")
    if collisions:
        print(f"      Коллизии ({len(collisions)}):")
        for src, info in collisions:
            print(f"        {src} → {info}")

    # Журнал переименований — рядом с папкой НТД
    log_path = NTD_DIR.parent / f"НТД_rename_log_{ts}.txt"
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write("# Журнал переименований (оригинал → новое имя)\n\n")
        for a, b in rename_log:
            fh.write(f"{a}\t→\t{b}\n")
    print(f"      Журнал переименований: {log_path}")

    # === Итог ===
    print()
    print("=" * 60)
    print("ГОТОВО (без бэкапа — деструктивно)")
    print(f"  Контент изменён в {content_changed}/{len(files)} файлах")
    print(f"  Переименовано      {renamed}/{len(files)} файлов")
    print("=" * 60)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
