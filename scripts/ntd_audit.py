"""Аудит папки НТД: ищет баги форматирования, битые ссылки, URL-мусор и прочее.

Не меняет файлы — только отчёт.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

NTD_DIR = Path(os.getenv("NTD_DIR", str(Path.home() / "Desktop" / "НТД")))


def audit_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    size = len(text)
    lines = text.splitlines()

    issues: list[str] = []

    # 1. Пустой файл
    if size == 0:
        issues.append("EMPTY_FILE")
        return {"issues": issues, "size": size, "lines": len(lines)}

    # 2. Подозрительно маленький
    if size < 500:
        issues.append(f"VERY_SMALL({size}b)")

    # 3. URL-encoded мусор в ссылках
    url_junk = re.findall(r"\(%22[^)]*%22[^)]*\)", text)
    if url_junk:
        issues.append(f"URL_ENCODED_JUNK({len(url_junk)})")

    # 4. Незакрытые/битые markdown-ссылки
    broken_links = re.findall(r"\]\(\s*\)", text)
    if broken_links:
        issues.append(f"EMPTY_LINKS({len(broken_links)})")

    # 5. Подозрительные ссылки типа "sub100", "bookmark123" — остатки Word
    word_bookmarks = re.findall(r"\]\([^)]*%5Cl%20%22[^)]*\)", text)
    if word_bookmarks:
        issues.append(f"WORD_BOOKMARKS({len(word_bookmarks)})")

    # 6. Множественные пустые строки (3+ подряд)
    triple_blank = len(re.findall(r"\n\n\n\n+", text))
    if triple_blank:
        issues.append(f"MULTI_BLANK({triple_blank})")

    # 7. Смешанные переносы строк
    if "\r\n" in text and "\n" in text.replace("\r\n", ""):
        issues.append("MIXED_LINE_ENDINGS")
    elif "\r\n" in text:
        issues.append("CRLF")

    # 8. Битые символы (replacement char — признак кривой кодировки)
    if "\ufffd" in text:
        issues.append(f"REPLACEMENT_CHAR({text.count(chr(0xFFFD))})")

    # 9. Нули в тексте (битый файл)
    if "\x00" in text:
        issues.append("NULL_BYTES")

    # 10. HTML-сущности (Word-экспорт часто оставляет &nbsp; &amp; и т.д.)
    html_entities = re.findall(r"&(?:nbsp|amp|lt|gt|quot|#\d+);", text)
    if html_entities:
        issues.append(f"HTML_ENTITIES({len(html_entities)})")

    # 11. Неудалённые Word-артефакты <a name="..."></a>
    word_anchors = re.findall(r"<a\s+name=", text, re.IGNORECASE)
    if word_anchors:
        issues.append(f"WORD_ANCHORS({len(word_anchors)})")

    # 12. Не-breaking space
    nbsp_count = text.count("\u00a0")
    if nbsp_count > 10:
        issues.append(f"NBSP({nbsp_count})")

    # 13. Табы вперемешку с пробелами
    if "\t" in text:
        issues.append(f"TABS({text.count(chr(9))})")

    # 14. Длинные строки без переноса (>2000 символов — часто склейка абзацев)
    longest = max((len(l) for l in lines), default=0)
    if longest > 3000:
        issues.append(f"VERY_LONG_LINE({longest})")

    # 15. Оглавление с битыми якорями
    toc_broken = len(re.findall(r"\[\s*[\d.]+\s+[^\]]+\]\(%22", text))
    if toc_broken:
        issues.append(f"BROKEN_TOC({toc_broken})")

    # 16. Кириллица в имени файла (для pipeline-совместимости)
    if re.search(r"[а-яА-ЯёЁ]", path.name):
        issues.append("CYRILLIC_FILENAME")

    # 17. Пробел в имени файла
    if " " in path.name:
        issues.append("SPACES_IN_FILENAME")

    # 18. Дубликаты разделителей `---` (могут сбить frontmatter)
    yaml_delims = text.count("\n---\n") + (1 if text.startswith("---\n") else 0)
    if yaml_delims > 2 and not text.startswith("---\n"):
        issues.append(f"STRAY_YAML_DELIMS({yaml_delims})")

    # 19. Строки-разрывы таблиц, но без заголовка (битая таблица)
    table_rows = re.findall(r"^\|.*\|$", text, re.MULTILINE)
    if table_rows:
        # Есть таблицы? Проверим, есть ли строки-разделители
        sep_rows = re.findall(r"^\|[\s\-:|]+\|$", text, re.MULTILINE)
        if len(table_rows) > 3 and not sep_rows:
            issues.append("BROKEN_TABLES")

    # 20. Наличие base64-картинок (раздувает размер)
    b64_imgs = re.findall(r"data:image/[^;]+;base64,", text)
    if b64_imgs:
        issues.append(f"BASE64_IMAGES({len(b64_imgs)})")

    return {
        "issues": issues,
        "size": size,
        "lines": len(lines),
        "longest_line": longest,
    }


def main() -> int:
    if not NTD_DIR.exists():
        print(f"ERR: папка не найдена: {NTD_DIR}")
        return 2

    files = sorted(NTD_DIR.glob("*.md"))
    if not files:
        print(f"ERR: .md-файлов не найдено в {NTD_DIR}")
        return 2

    print(f"Сканирую {len(files)} файлов в {NTD_DIR}\n")

    all_issues: Counter[str] = Counter()
    per_file: list[tuple[Path, dict]] = []
    clean_count = 0

    for f in files:
        try:
            report = audit_file(f)
        except Exception as e:  # noqa: BLE001
            report = {"issues": [f"SCAN_ERROR: {e}"], "size": 0, "lines": 0}

        per_file.append((f, report))
        structural_issues = [
            i for i in report["issues"]
            if not i.startswith(("CYRILLIC_FILENAME", "SPACES_IN_FILENAME"))
        ]
        if not structural_issues:
            clean_count += 1
        for issue in report["issues"]:
            key = issue.split("(")[0]
            all_issues[key] += 1

    # ============ ОТЧЁТ ============
    print("=" * 72)
    print("СВОДКА ПО ТИПАМ ПРОБЛЕМ")
    print("=" * 72)
    for issue_type, count in all_issues.most_common():
        print(f"  {issue_type:30s} {count:5d} файл(ов)")

    print()
    print("=" * 72)
    print("ТОП-20 ФАЙЛОВ С НАИБОЛЬШИМ ЧИСЛОМ ПРОБЛЕМ")
    print("=" * 72)
    ranked = sorted(
        per_file,
        key=lambda x: len([i for i in x[1]["issues"]
                           if not i.startswith(("CYRILLIC", "SPACES"))]),
        reverse=True,
    )
    for path, rep in ranked[:20]:
        structural = [
            i for i in rep["issues"]
            if not i.startswith(("CYRILLIC", "SPACES"))
        ]
        if not structural:
            continue
        print(f"\n  {path.name}")
        print(f"    размер: {rep['size']:,}b, строк: {rep['lines']:,}")
        for i in rep["issues"]:
            print(f"      - {i}")

    print()
    print("=" * 72)
    print(f"ИТОГО: {len(files)} файлов")
    print(f"  Чистых (без структурных багов): {clean_count}")
    print(f"  С багами:                        {len(files) - clean_count}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
