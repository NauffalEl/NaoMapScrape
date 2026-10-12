"""Filter exported leads: keep only rows with no website that do have a phone.

Usage:
    python scripts/filter_leads.py data/exports/leads.csv data/exports/out.csv
"""

import csv
import sys


def filter_rows(src: str, dst: str) -> tuple:
    with open(src, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames

    kept = [
        r
        for r in rows
        if not r.get("website", "").strip() and r.get("phone", "").strip()
    ]

    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept)

    return len(rows), len(kept)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    total, kept = filter_rows(sys.argv[1], sys.argv[2])
    print(f"total={total} no_website_with_phone={kept} -> {sys.argv[2]}")
