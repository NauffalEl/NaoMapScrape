"""Google Maps browser automation — navigation and search."""

import asyncio
import logging
import re
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

    async def open_detail_panel(self, card, expect_name: Optional[str] = None):
        """Click a result card and return the detail panel handle.

        Contact rows (phone, website) are only rendered inside the detail
        panel, never on the feed card, so callers must open it before
        enriching. Several role="region" nodes coexist and the detail panel
        is the one carrying data-item-id="address"; role="dialog" matches an
        invisible overlay instead.

        expect_name is the card's business name. Google keeps the previous
        panel mounted for a moment, so without this guard the query returns
        the *previous* card's panel and every lead inherits its phone/website.
        Waiting for the title to change is what keeps rows aligned.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")
        try:
            await card.scroll_into_view_if_needed(timeout=4000)
            await card.click(timeout=6000)
        except Exception as exc:
            logger.debug("Card click failed: %s", exc)
            return None

        if expect_name:
            needle = re.sub(r"\s+", " ", expect_name).strip()[:24].lower()
            try:
                await self.page.wait_for_function(
                    """(needle) => {
                        const panel = document.querySelector(
                            'div[role="region"]:has([data-item-id="address"])');
                        if (!panel) return false;
                        const h1 = panel.querySelector('h1, .DUwDvf, [class*="title"]');
                        return !!h1 && h1.textContent.toLowerCase().includes(needle);
                    }""",
                    arg=needle,
                    timeout=6000,
                )
            except Exception:
                logger.debug("Panel title never matched %r", needle)

        try:
            await self.page.wait_for_selector(
                'div[role="region"] [data-item-id="address"]', timeout=6000
            )
        except Exception:
            return None

        return await self.page.query_selector(
            'div[role="region"]:has([data-item-id="address"])'
        )

    async def close_detail_panel(self) -> None:
        """Dismiss the detail panel so the feed is usable again.

        Escape is tried first because the close button is inside the panel
        Google just re-rendered, so querying it races the re-render. Escape
        is idempotent and leaves the feed untouched.
        """
        if not self.page:
            return
        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass
        # Wait until the panel is actually gone, otherwise the next card's
        # click lands on the overlay instead of the feed.
        try:
            await self.page.wait_for_function(
                "() => !document.querySelector("
                "'div[role=\"region\"] [data-item-id=\"address\"]')",
                timeout=5000,
            )
        except Exception:
            logger.debug("Detail panel did not close in time")
        await self.page.wait_for_timeout(300)

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
