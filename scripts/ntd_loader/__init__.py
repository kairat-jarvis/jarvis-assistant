"""ntd_loader — загрузчик НТД из PDF в локальный expertise_ntd с SQLite-журналом.

Pipeline:
  PDF → vypiska_ird.ocr_waterfall (L1 pdfplumber → L2 PaddleOCR-VL-1.5 → L3 Claude Vision)
      → parser.parse_clauses
      → OpenAI text-embedding-3-small (batched)
      → pg_store.upsert_document + upsert_clauses → postgres expertise_ntd
      → journal.* (SQLite, data/ntd_ingest.db)

CLI:
  python -m scripts.ntd_loader <pdf> [--doc-code 'СН РК ...'] [--dry-run] [--force]
  python -m scripts.ntd_loader --list             # последние прогоны
  python -m scripts.ntd_loader --show <run_id>    # детали прогона
"""
from .loader import load_pdf, LoadResult  # noqa: F401
