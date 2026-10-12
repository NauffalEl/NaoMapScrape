"""Normalizer — clean raw extracted strings into typed values.

Rules:
  Phone:   "0812 3456 789" -> "08123456789"
  Rating:  "4,7"          -> 4.7
  Reviews: "1.2K" -> 1200, "2.3M" -> 2300000, "1,2RB" -> 1200, "1,5JT" -> 1500000
  Website status: HAS_WEBSITE | NO_WEBSITE_DETECTED | UNKNOWN
"""

import re
from typing import Optional


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Strip formatting and return a plausible Indonesian number.

    Google mixes number shapes: "0812-3456-7890", "+62 812 3456 7890" and
    "62-812-3456-7890". Stripping non-digits turns the latter two into 12+
    digits, so a leading country code is trimmed back to the local form.
    13 digits is allowed because some listings genuinely publish an extra
    digit — dropping the whole lead over a suspect number costs a business.
    """
    if not raw:
        return None
    cleaned = re.sub(r"[^\d]", "", raw)
    if cleaned.startswith("0"):
        local = cleaned
    elif cleaned.startswith("62"):
        local = "0" + cleaned[2:]
    else:
        local = cleaned
    return local if 9 <= len(local) <= 13 else None


def normalize_rating(raw: Optional[float]) -> Optional[float]:
    """Parse a rating, clamped to 0–5.

    Cards render the score glued to its review count ("4,9(1.094)"), so the
    leading score is taken and the parenthetical dropped rather than failing
    the whole parse.
    """
    if raw is None:
        return None
    text = str(raw).split("(")[0].strip().replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    return round(max(0.0, min(5.0, value)), 1)


def normalize_review_count(raw: Optional[str]) -> Optional[int]:
    """Parse a review count, expanding K/M/RB/JT suffixes."""
    if raw is None:
        return None

    cleaned = re.sub(r"[()+\s]", "", str(raw)).strip()
    if not cleaned:
        return None

    suffixes = {"k": 1_000, "rb": 1_000, "m": 1_000_000, "jt": 1_000_000}
    multiplier = 1
    match = re.search(r"([a-zA-Z]+)$", cleaned)
    if match:
        suffix = match.group(1).lower()
        if suffix in suffixes:
            multiplier = suffixes[suffix]
            cleaned = cleaned[: -len(suffix)]

    if multiplier > 1:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = re.sub(r"[.,]", "", cleaned)

    try:
        value = float(cleaned)
    except ValueError:
        return None
    return int(round(value * multiplier))


def normalize_address(raw: Optional[str]) -> Optional[str]:
    """Collapse whitespace and trim."""
    if not raw:
        return None
    return re.sub(r"\s+", " ", raw).strip() or None


def resolve_website(raw: Optional[str]) -> tuple:
    """Return (website, website_status)."""
    if raw and raw.startswith("http"):
        return raw, "HAS_WEBSITE"
    if raw:
        return raw, "UNKNOWN"
    return None, "NO_WEBSITE_DETECTED"


def normalize_category(raw: Optional[str]) -> Optional[str]:
    """First line of the category, with hours/price fragments removed.

    A card row can carry the category and the opening hours glued together by
    a newline ("Kafe\\nBuka"), so splitting on lines keeps only the category.
    """
    if not raw:
        return None
    first = raw.strip().splitlines()[0].strip()
    first = re.sub(r"\s*[·|]\s*(Buka|Tutup|Open|Closed).*$", "", first, flags=re.I)
    first = re.sub(r"\s*[·|]\s*Rp\s.*$", "", first, flags=re.I).strip()
    return first or None


def normalize(raw: dict) -> dict:
    """Normalize a raw extractor dict into clean fields."""
    website, website_status = resolve_website(raw.get("raw_website"))
    return {
        "name": (raw.get("raw_name") or "").strip() or None,
        "category": normalize_category(raw.get("raw_category")),
        "address": normalize_address(raw.get("raw_address")),
        "phone": normalize_phone(raw.get("raw_phone")),
        "rating": normalize_rating(raw.get("raw_rating")),
        "review_count": normalize_review_count(raw.get("raw_review_count")),
        "website": website,
        "website_status": website_status,
        "maps_url": raw.get("raw_maps_url"),
        "opening_status": raw.get("raw_opening_status"),
    }


class Normalizer:
    """Object wrapper for the module-level normalize helpers."""

    def normalize(self, raw: dict) -> dict:
        return normalize(raw)
