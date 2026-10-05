"""Lead model — plain dataclass that mirrors the DB schema.

Kept separate from SQLAlchemy so the scraper never depends on the ORM.
"""

import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Lead:
    name: Optional[str] = None
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    website: Optional[str] = None
    website_status: Optional[str] = None
    maps_url: Optional[str] = None
    keyword_query: Optional[str] = None
    location_query: Optional[str] = None
    opening_status: Optional[str] = None
    collected_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    id: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        """Build a Lead from a parser dict, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)