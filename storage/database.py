"""Database — thin SQLite wrapper (stdlib sqlite3, no ORM needed)."""

import datetime
import logging
import sqlite3
from typing import List, Optional

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    address TEXT,
    phone TEXT,
    rating REAL,
    review_count INTEGER,
    website TEXT,
    website_status TEXT,
    maps_url TEXT,
    keyword_query TEXT,
    location_query TEXT,
    opening_status TEXT,
    collected_at TEXT
);
"""


class Database:
    """SQLite-backed lead store."""

    def __init__(self, db_path: str = "data/naomapscrape.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def init(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        logger.info("DB initialised at %s", self.db_path)

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.init()
        assert self._conn is not None
        return self._conn

    def save(self, lead) -> int:
        """Insert a lead (dataclass or dict). Returns the row id."""
        d = lead.to_dict() if hasattr(lead, "to_dict") else lead
        d["collected_at"] = d.get("collected_at") or datetime.datetime.utcnow().isoformat()
        cur = self.conn.execute(
            """INSERT INTO leads
               (name, category, address, phone, rating, review_count,
                website, website_status, maps_url, keyword_query,
                location_query, opening_status, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                d.get("name"), d.get("category"), d.get("address"),
                d.get("phone"), d.get("rating"), d.get("review_count"),
                d.get("website"), d.get("website_status"), d.get("maps_url"),
                d.get("keyword_query"), d.get("location_query"),
                d.get("opening_status"), d.get("collected_at"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def save_many(self, leads: list) -> int:
        saved = 0
        for lead in leads:
            self.save(lead)
            saved += 1
        return saved

    def get_all(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str) -> List[dict]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """SELECT * FROM leads
               WHERE name LIKE ? OR address LIKE ? OR phone LIKE ? OR category LIKE ?
               ORDER BY id DESC""",
            (like, like, like, like),
        ).fetchall()
        return [dict(r) for r in rows]

    def filter(
        self,
        website: Optional[str] = None,
        min_rating: Optional[float] = None,
        min_reviews: Optional[int] = None,
        location: Optional[str] = None,
    ) -> List[dict]:
        sql = "SELECT * FROM leads WHERE 1=1"
        params: list = []
        if website and website.upper() in ("HAS_WEBSITE", "NO_WEBSITE_DETECTED"):
            sql += " AND website_status = ?"
            params.append(website.upper())
        if min_rating is not None:
            sql += " AND rating >= ?"
            params.append(min_rating)
        if min_reviews is not None:
            sql += " AND review_count >= ?"
            params.append(min_reviews)
        if location:
            sql += " AND location_query LIKE ?"
            params.append(f"%{location}%")
        sql += " ORDER BY id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def delete(self, lead_ids: List[int]) -> int:
        placeholders = ",".join("?" for _ in lead_ids)
        cur = self.conn.execute(
            f"DELETE FROM leads WHERE id IN ({placeholders})", lead_ids
        )
        self.conn.commit()
        return cur.rowcount

    def clear(self) -> None:
        self.conn.execute("DELETE FROM leads")
        self.conn.commit()

    def stats(self) -> dict:
        row = self.conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN website_status='HAS_WEBSITE' THEN 1 ELSE 0 END) AS has_website,
                 SUM(CASE WHEN website_status='NO_WEBSITE_DETECTED' THEN 1 ELSE 0 END) AS no_website,
                 SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) AS phone_available,
                 AVG(rating) AS avg_rating
               FROM leads"""
        ).fetchone()
        if row and row["total"]:
            return {
                "total": row["total"],
                "has_website": row["has_website"] or 0,
                "no_website": row["no_website"] or 0,
                "phone_available": row["phone_available"] or 0,
                "avg_rating": round(row["avg_rating"], 2),
            }
        return {"total": 0, "has_website": 0, "no_website": 0, "phone_available": 0, "avg_rating": 0}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None