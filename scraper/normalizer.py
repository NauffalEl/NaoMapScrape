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
    """Strip everything except digits and a leading '+'."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.count("+") > 0 and not cleaned.startswith("+"):
        cleaned = cleaned.replace("+", "")
    if cleaned.startswith("+"):
        cleaned = "+" + cleaned[1:].replace("+", "")
    return cleaned or None


def normalize_rating(raw: Optional[str]) -> Optional[float]:
    """Parse a rating, comma or dot decimal, clamped to 0–5."""
    if raw is None:
        return None
    try:
        value = float(str(raw).replace(",", "."))
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


def normalize(raw: dict) -> dict:
    """Normalize a raw extractor dict into clean fields."""
    website, website_status = resolve_website(raw.get("raw_website"))
    return {
        "name": (raw.get("raw_name") or "").strip() or None,
        "category": (raw.get("raw_category") or "").strip() or None,
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
