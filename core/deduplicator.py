"""Deduplicator — drop duplicate leads by a priority of identifiers.

Priority:
  1. maps_url
  2. name + address (normalised)
  3. name + phone
"""

import re
from typing import Dict, List


def _norm(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _fingerprint(lead: dict) -> str:
    """Primary fingerprint: maps_url if present, else name+address, else name+phone."""
    if lead.get("maps_url"):
        return "url:" + _norm(lead["maps_url"])
    name = _norm(lead.get("name"))
    address = _norm(lead.get("address"))
    if name and address:
        return f"na:{name}|{address}"
    phone = _norm(lead.get("phone"))
    return f"np:{name}|{phone}"


class Deduplicator:
    """Keeps a seen-set of fingerprints across a collection run."""

    def __init__(self):
        self._seen: Dict[str, dict] = {}

    def is_duplicate(self, lead: dict) -> bool:
        """True if this lead matches one already seen."""
        fp = _fingerprint(lead)
        if fp in self._seen:
            return True

        # Cross-checks: same name + address, or same name + phone, even
        # when maps_url differs (e.g. slightly different URL params).
        name = _norm(lead.get("name"))
        address = _norm(lead.get("address"))
        phone = _norm(lead.get("phone"))
        for seen in self._seen.values():
            if name and name == _norm(seen.get("name")):
                if address and address == _norm(seen.get("address")):
                    return True
                if phone and phone == _norm(seen.get("phone")):
                    return True
        return False

    def add(self, lead: dict) -> None:
        self._seen[_fingerprint(lead)] = lead

    def filter(self, leads: List[dict]) -> List[dict]:
        """Return only non-duplicate leads and register them."""
        unique = []
        for lead in leads:
            if self.is_duplicate(lead):
                continue
            self.add(lead)
            unique.append(lead)
        return unique

    def reset(self) -> None:
        self._seen.clear()

    @property
    def count(self) -> int:
        return len(self._seen)
