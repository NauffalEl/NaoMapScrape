"""Self-check for the scraper's normalisation rules.

Run: python scripts/selftest.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.normalizer import (  # noqa: E402
    normalize_category,
    normalize_phone,
    normalize_rating,
)


def check_phone():
    cases = [
        ("0812-3456-7890", "081234567890"),   # dashes stripped
        ("0812 3456 7890", "081234567890"),   # spaces stripped
        ("+62 812 3456 7890", "081234567890"),  # country code -> local
        ("6281234567890", "081234567890"),    # bare country code -> local
        ("8123456789", "8123456789"),        # no leading 0, kept as-is
        ("0895329251415", "0895329251415"),  # 13d listing, kept not dropped
        ("12345", None),                     # too short to be dialable
        ("", None),
        (None, None),
    ]
    for raw, want in cases:
        got = normalize_phone(raw)
        assert got == want, f"normalize_phone({raw!r}) = {got!r}, want {want!r}"


def check_rating():
    cases = [
        ("4,9", 4.9),
        ("4.9", 4.9),
        (4.9, 4.9),
        ("4,9(1.094)", 4.9),   # review count appended
        ("9,9", 5.0),          # clamped to the 0-5 scale
        ("abc", None),
    ]
    for raw, want in cases:
        got = normalize_rating(raw)
        assert got == want, f"normalize_rating({raw!r}) = {got!r}, want {want!r}"


def check_category():
    cases = [
        ("Kedai Kopi", "Kedai Kopi"),
        ("Kafe\nBuka", "Kafe"),            # hours glued on a second line
        ("Kafe · Buka · Tutup pukul 22.00", "Kafe"),
        ("Masakan Asia · Rp 25–50 rb", "Masakan Asia"),
        ("", None),
        (None, None),
    ]
    for raw, want in cases:
        got = normalize_category(raw)
        assert got == want, f"normalize_category({raw!r}) = {got!r}, want {want!r}"


if __name__ == "__main__":
    check_phone()
    check_rating()
    check_category()
    print("selftest OK")