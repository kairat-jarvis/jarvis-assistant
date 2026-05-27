#!/usr/bin/env python3
"""Open a generated dashboard HTML file in the default browser for visual verification.

Usage:
    python open_dashboard.py <path-to-html>
    python open_dashboard.py "G:/Мой диск/AI/Claude Code/Excel/Interactiv Dashboard/portfolio_2026-04-25.html"
"""
import sys
import webbrowser
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    if path.suffix.lower() != ".html":
        print(f"WARN: expected .html, got {path.suffix}", file=sys.stderr)

    url = path.as_uri()
    print(f"Opening: {url}")
    webbrowser.open(url, new=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
