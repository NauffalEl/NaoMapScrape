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
                    cards = await self.scraper.search(item.keyword, item.location)
                    raw = await self.extractor.extract_all(cards)

                    # Phone/website only exist in the detail panel, so open it
                    # per card and enrich. The feed is re-queried on every
                    # iteration: opening/closing the panel re-renders the list
                    # and makes a cached ElementHandle click the wrong card.
                    #
                    # Only the cards that can still land in the output are
                    # enriched. Opening a panel costs seconds, so walking the
                    # whole feed past `limit` wasted most of the runtime.
                    if self.details:
                        remaining = limit - len(collected)
                        if remaining > 0:
                            raw = raw[:remaining]

                        enriched = []
                        for idx, data in enumerate(raw):
                            feed = await self.scraper.page.query_selector_all(
                                'div[role="article"]'
                            )
                            if idx >= len(feed):
                                break
                            panel = await self.scraper.open_detail_panel(
                                feed[idx], expect_name=data.get("raw_name")
                            )
                            if panel:
                                data = await self.extractor.extract_detail(panel, data)
                            await self.scraper.close_detail_panel()
                            enriched.append(data)
                        raw = enriched
                        logger.info(
                            "Enriched %d cards from detail panels", len(enriched)
                        )

                    leads = self.parser.parse_all(raw, item.keyword, item.location)
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
