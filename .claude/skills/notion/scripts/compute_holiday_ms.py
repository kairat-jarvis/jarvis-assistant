"""Compute Unix millisecond timestamps (UTC midnight) for a list of dates.

Use the output directly inside Notion formulas as `fromTimestamp(<ms>)`
constants — needed because `parseDate("YYYY-MM-DD")` is incompatible with
property dates in `dateBetween(...)` comparisons.

Usage:
    python compute_holiday_ms.py 2027-01-01 2027-03-22 2027-05-01
    python compute_holiday_ms.py --list path/to/dates.txt
    cat dates.txt | python compute_holiday_ms.py -
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys


def to_ms(iso_date: str) -> int:
    d = dt.datetime.fromisoformat(iso_date).replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def read_dates(args: list[str]) -> list[str]:
    if not args:
        return []
    if args[0] == "-":
        return [ln.strip() for ln in sys.stdin if ln.strip() and not ln.startswith("#")]
    if args[0] == "--list":
        if len(args) < 2:
            raise SystemExit("--list requires a file path")
        lines = pathlib.Path(args[1]).read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return args


def main() -> int:
    dates = read_dates(sys.argv[1:])
    if not dates:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    for iso in dates:
        try:
            ms = to_ms(iso)
        except ValueError as e:
            print(f"# SKIP: {iso!r} — {e}", file=sys.stderr)
            continue
        print(f"{iso}  →  {ms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
