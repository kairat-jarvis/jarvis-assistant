"""Smoke-test PaddleOCRVL v1.5 на одном PDF.

Запуск: .venv-paddle/bin/python -m scripts.ntd_loader._paddle_smoke <pdf>
Stdout: JSON {"pages": [{"page_no": N, "text": "...", "n_blocks": K}, ...], "elapsed_sec": ...}
Stderr: прогресс.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from paddleocr import PaddleOCRVL


def _extract_text_from_result(res) -> tuple[str, int]:
    """PaddleOCRVL.predict() → list[OCRResult]. У каждого OCRResult есть .res / .markdown / .json."""
    # Пробуем разные атрибуты, которые отдаёт PaddleOCR 3.5 для VL-пайплайна.
    md = getattr(res, "markdown", None)
    if md is not None:
        # md — обычно dict с 'markdown_texts' (str) и 'markdown_images' (dict).
        if isinstance(md, dict):
            txt = md.get("markdown_texts") or ""
        else:
            txt = str(md)
        # n_blocks неизвестен — берём по числу '\n\n'.
        return txt, txt.count("\n\n") + 1 if txt else 0
    data = getattr(res, "json", None) or getattr(res, "res", None)
    if isinstance(data, dict):
        blocks = data.get("parsing_res_list") or data.get("layout_parsing_res") or []
        parts = []
        for b in blocks:
            t = b.get("block_content") or b.get("text") or ""
            if t:
                parts.append(t)
        return "\n\n".join(parts), len(blocks)
    return repr(res), 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ... _paddle_smoke <pdf>", file=sys.stderr)
        return 2
    pdf = Path(argv[1]).resolve()
    if not pdf.is_file():
        print(f"not a file: {pdf}", file=sys.stderr)
        return 2

    print(f"[paddle] init PaddleOCRVL (pipeline_version=v1.5)…", file=sys.stderr, flush=True)
    t0 = time.time()
    pipe = PaddleOCRVL()  # v1.5 по умолчанию
    print(f"[paddle] init done in {time.time() - t0:.1f}s", file=sys.stderr, flush=True)

    t1 = time.time()
    print(f"[paddle] predict on {pdf.name}…", file=sys.stderr, flush=True)
    out = pipe.predict(str(pdf))
    results = list(out) if not isinstance(out, list) else out
    elapsed = time.time() - t1
    print(f"[paddle] predict done: {len(results)} page(s) in {elapsed:.1f}s",
          file=sys.stderr, flush=True)

    pages = []
    for i, r in enumerate(results, start=1):
        text, n_blocks = _extract_text_from_result(r)
        pages.append({"page_no": i, "text": text, "n_blocks": n_blocks, "len": len(text)})
        print(f"[paddle]   стр.{i}: {len(text)} chars, {n_blocks} blocks",
              file=sys.stderr, flush=True)

    payload = {"pdf": str(pdf), "pages": pages, "elapsed_sec": elapsed}
    json.dump(payload, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
