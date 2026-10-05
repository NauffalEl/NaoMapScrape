"""Google Maps browser automation — navigation and search."""

import asyncio
import logging
from typing import List, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class GoogleMapsScraper:
    """Controls a headless Chromium browser to query Google Maps."""

    BASE_URL = "https://www.google.com/maps/search/"

    def __init__(self, headless: bool = True, timeout: int = 15000):
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self.browser = None
        self.page = None

    async def start(self):
        """Launch the browser and open a fresh page."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await self.browser.new_context(
            locale="id-ID",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self.page = await context.new_page()
        logger.info("Browser started (headless=%s)", self.headless)

    async def stop(self):
        """Close browser and stop Playwright."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser stopped")

    def build_search_url(self, keyword: str, location: str) -> str:
        """Build a Google Maps search URL for keyword + location."""
        query = f"{keyword} {location}".strip().replace(" ", "+")
        return f"{self.BASE_URL}{query}"

    async def search(self, keyword: str, location: str, max_scrolls: int = 15) -> List[dict]:
        """Navigate, load results, and return raw business card elements.

        Returns a list of ElementHandle objects wrapped so the extractor can
        read them. Kept browser-facing only; parsing lives in extractor/parser.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        url = self.build_search_url(keyword, location)
        logger.info("Navigating to %s", url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

        try:
            await self.page.wait_for_selector('div[role="article"]', timeout=self.timeout)
        except Exception:
            logger.warning("No result cards appeared for %s / %s", keyword, location)
            return []

        await self._scroll_results(max_scrolls)

        cards = await self.page.query_selector_all('div[role="article"]')
        logger.info("Found %d cards for %s / %s", len(cards), keyword, location)
        return cards

    async def _scroll_results(self, max_scrolls: int):
        """Scroll the results feed until the bottom is reached."""
        feed = await self.page.query_selector('div[role="feed"]')
        for i in range(max_scrolls):
            if feed:
                await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            else:
                await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.page.wait_for_timeout(1200)

            end_marker = await self.page.query_selector(
                'span.HlvSq, p.fontBodyMedium span'
            )
            if end_marker:
                text = (await end_marker.inner_text()).lower()
                if "end of the list" in text or "akhir daftar" in text:
                    logger.info("Reached end of results after %d scrolls", i + 1)
                    break
        logger.debug("Finished scrolling after up to %d scrolls", max_scrolls)
