"""Merge lead CSVs, keeping the richest row per business name.

Usage:
    python scripts/merge_leads.py out.csv in1.csv in2.csv [...]

Later files win per field, so re-running a keyword after an extractor fix
repairs only the fields that changed.
"""

import csv
import sys
from collections import OrderedDict


# Markers of a field that parsed into junk. A later file can still have the
# real value, so these count as empty when comparing rows.
JUNK = ("Rp ", "Buka ·", "Tutup pukul", "Tidak ada ulasan", "\n")


def _usable(row: dict, key: str) -> str:
    value = (row.get(key) or "").strip()
    return "" if any(m in value for m in JUNK) else value


def richness(row: dict) -> int:
    """How many contact/detail fields a row actually carries."""
    return sum(1 for key in ("phone", "website", "address", "category", "rating", "review_count") if _usable(row, key))


def merge(srcs, dst: str) -> tuple:
    merged: "OrderedDict[str, dict]" = OrderedDict()
    total = 0

    for src in srcs:
        with open(src, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        total += len(rows)
        for row in rows:
            key = (row.get("name") or "").strip().lower()
            prev = merged.get(key)
            # Take the new row wholesale when it carries more, else fill only
            # the blanks — that is what repairs a field after a fix.
            if prev is None or richness(row) > richness(prev):
                merged[key] = dict(row)
            else:
                for k in row:
                    if not _usable(prev, k) and _usable(row, k):
                        prev[k] = row[k]

    out = list(merged.values())
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    return total, len(out)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(1)
    total, unique = merge(sys.argv[2:], sys.argv[1])
    print(f"merged {total} rows -> {unique} unique -> {sys.argv[1]}")