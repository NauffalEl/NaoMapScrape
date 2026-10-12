"""Collector — orchestrates scraping across a queue of jobs."""

import logging
from typing import Callable, List, Optional

from scraper.google_maps import GoogleMapsScraper
from scraper.extractor import Extractor
from scraper.parser import Parser
from storage.database import Database
from storage.models import Lead
from core.queue import Queue, QueueItem
from core.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class Collector:
    """Runs the full pipeline: search -> extract -> parse -> dedupe -> store."""

    def __init__(
        self,
        headless: bool = True,
        db_path: str = "data/naomapscrape.db",
        on_progress: Optional[Callable[[dict], None]] = None,
        details: bool = True,
    ):
        self.scraper = GoogleMapsScraper(headless=headless)
        self.extractor = Extractor()
        self.parser = Parser()
        self.deduplicator = Deduplicator()
        self.db = Database(db_path)
        self.queue = Queue()
        self.on_progress = on_progress
        self.details = details
        self._stop = False
        # Place URLs already visited, so a place found under a second keyword
        # or location is not loaded again just to rediscover the same fields.
        self._seen_urls: set = set()

    async def run(
        self,
        keywords: List[str],
        locations: List[str],
        limit: int = 100,
        website_filter: str = "ALL",
    ) -> List[dict]:
        """Run the full collection. Returns the list of stored leads."""
        self.queue.build(keywords, locations)
        self.db.init()
        await self.scraper.start()

        collected: List[dict] = []
        try:
            item = self.queue.next()
            while item and not self._stop and len(collected) < limit:
                self.queue.mark_running(item)
                self._emit("running", item, len(collected))

                try:
                    rows = await self.scraper.search(item.keyword, item.location)

                    # Phone/website only exist on the place page, so each card
                    # is enriched by navigating to its own href. Opening a
                    # place costs seconds, so only the cards that can still
                    # land in the output are visited — walking the whole feed
                    # past `limit` wasted most of the runtime.
                    if self.details:
                        remaining = limit - len(collected)
                        if remaining > 0:
                            rows = rows[:remaining]

                        # Drop places already seen before navigating. The full
                        # deduplicator needs the phone and address, which only
                        # exist on the place page, so it cannot run first; the
                        # place URL is already on the feed and is a stable
                        # identifier, which is enough to skip the visit.
                        unseen = []
                        for row in rows:
                            url = row.get("raw_maps_url") or row.get("href")
                            if url and url in self._seen_urls:
                                continue
                            if url:
                                self._seen_urls.add(url)
                            unseen.append(row)
                        if len(unseen) < len(rows):
                            logger.info(
                                "Skipping %d already-seen places",
                                len(rows) - len(unseen),
                            )

                        enriched = []
                        for row in unseen:
                            panel = await self.scraper.open_place(
                                row["href"], expect_name=row.get("raw_name")
                            )
                            if panel:
                                row = await self.extractor.extract_detail(panel, row)
                            enriched.append(row)
                        rows = enriched
                        logger.info("Enriched %d cards from place pages", len(rows))

                    leads = self.parser.parse_all(rows, item.keyword, item.location)
                    leads = self._apply_website_filter(leads, website_filter)
                    fresh = self.deduplicator.filter(leads)

                    for lead in fresh:
                        if len(collected) >= limit:
                            break
                        self.db.save(Lead.from_dict(lead))
                        collected.append(lead)

                    self.queue.mark_complete(item, len(fresh))
                    logger.info(
                        "%s x %s -> %d new (%d total)",
                        item.keyword, item.location, len(fresh), len(collected),
                    )
                except Exception as exc:
                    logger.exception("Job failed: %s", exc)
                    self.queue.mark_failed(item, str(exc))

                self._emit("progress", item, len(collected))
                item = self.queue.next()
        finally:
            await self.scraper.stop()

        self._emit("done", None, len(collected))
        return collected

    def stop(self) -> None:
        """Request a graceful stop after the current job."""
        self._stop = True

    @staticmethod
    def _apply_website_filter(leads: List[dict], website_filter: str) -> List[dict]:
        f = (website_filter or "ALL").upper()
        if f == "HAS_WEBSITE":
            return [l for l in leads if l.get("website_status") == "HAS_WEBSITE"]
        if f in ("NO_WEBSITE", "NO_WEBSITE_DETECTED"):
            return [l for l in leads if l.get("website_status") == "NO_WEBSITE_DETECTED"]
        return leads

    def _emit(self, event: str, item: Optional[QueueItem], total: int) -> None:
        if not self.on_progress:
            return
        payload = {"event": event, "collected": total, "stats": self.queue.stats()}
        if item:
            payload["keyword"] = item.keyword
            payload["location"] = item.location
        self.on_progress(payload)
