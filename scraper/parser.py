"""Parser — turn raw extractor dicts into structured Lead dictionaries."""

from typing import List, Optional

from .normalizer import normalize


def _generate_id(raw: dict) -> str:
    """Deterministic short id from name + address + phone."""
    seed = "|".join(
        str(raw.get(k) or "") for k in ("raw_name", "raw_address", "raw_phone")
    )
    h = 0
    for ch in seed:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return f"lead_{h:x}"


def parse_lead(raw: dict, keyword: str = "", location: str = "") -> dict:
    """Parse a single raw dict into a structured lead."""
    norm = normalize(raw)
    return {
        "id": _generate_id(raw),
        "name": norm["name"],
        "category": norm["category"],
        "address": norm["address"],
        "phone": norm["phone"],
        "rating": norm["rating"],
        "review_count": norm["review_count"],
        "website": norm["website"],
        "website_status": norm["website_status"],
        "maps_url": norm["maps_url"],
        "keyword_query": keyword,
        "location_query": location,
        "opening_status": norm["opening_status"],
    }


class Parser:
    """Parses lists of raw extractor dicts into leads."""

    def parse_all(
        self, raw_results: Optional[List[dict]], keyword: str = "", location: str = ""
    ) -> List[dict]:
        if not raw_results:
            return []
        return [parse_lead(raw, keyword, location) for raw in raw_results]
