"""Smoke-test Claude PDF API на одном PDF (модель — из CLAUDE_PDF_MODEL).

Запуск: .venv/bin/python scripts/ntd_loader/_claude_pdf_smoke.py <pdf>
Stdout: JSON {"pdf": "...", "model": "...", "n_chunks": N,
              "pages": [{"page_no": N, "text": "...", "len": L}],
              "full_text_len": L, "elapsed_sec": T}
Stderr: прогресс.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

# Подхватываем .env вручную (без dotenv).
_env = _PROJECT_ROOT / ".env"
if _env.is_file():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from scripts.ntd_loader.pdf_extract import extract_pdf, DEFAULT_MODEL  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: _claude_pdf_smoke.py <pdf>", file=sys.stderr)
        return 2
    pdf = Path(argv[1]).resolve()
    if not pdf.is_file():
        print(f"not a file: {pdf}", file=sys.stderr)
        return 2

    model = os.environ.get("CLAUDE_PDF_MODEL", DEFAULT_MODEL)
    print(f"[claude-pdf] model={model}", file=sys.stderr, flush=True)
    t0 = time.time()
    full_text, pages = extract_pdf(
        str(pdf),
        model=model,
        progress=lambda s: print(s, file=sys.stderr, flush=True),
    )
    elapsed = time.time() - t0
    print(
        f"[claude-pdf] done: {len(pages)} pages, "
        f"{len(full_text)} chars in {elapsed:.1f}s",
        file=sys.stderr,
        flush=True,
    )

    pages_out = [
        {"page_no": i + 1, "text": p.text, "len": len(p.text),
         "tier": p.tier, "confidence": p.confidence,
         "fallback_reason": p.fallback_reason}
        for i, p in enumerate(pages)
    ]
    payload = {
        "pdf": str(pdf),
        "model": model,
        "n_pages": len(pages),
        "full_text_len": len(full_text),
        "pages": pages_out,
        "elapsed_sec": elapsed,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
