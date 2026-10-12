"""Google Maps browser automation — navigation and search."""

import asyncio
import logging
import re
from typing import List, Optional
from urllib.parse import unquote_plus

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def _slug_matches(slug: str, name: str) -> bool:
    """Is the URL slug the same business as the card name?

    Both sides lose punctuation and accents before comparing, so
    "Saint Social - Coffee & Space" and "Saint+Social+%E2%80%94+Coffee"
    match. A short slug is accepted as a prefix of the name because Maps
    truncates long names in the path.
    """
    a, b = _norm(unquote_plus(slug)), _norm(name)
    if not a or not b:
        return True
    if a == b:
        return True
    # Compare on a leading run of words; Maps may append "& ..." or truncate.
    return a.startswith(b) or b.startswith(a)


# One evaluate() that returns every raw field for every card.
#
# This lives in JS rather than as a chain of Playwright selector calls
# because the feed is navigated away from during enrichment, which invalidates
# every ElementHandle taken against it. Reading the whole feed in a single
# call also guarantees the href of a card and the fields filed under it come
# from the same instant, which the previous click-then-read flow could not.
#
# The row parsing mirrors _row_pair / _address / _category in extractor.py:
# Google packs "category · street" into one W4Efsd div and puts the rating
# and the hours in sibling divs, so the pair is split on the separator rather
# than read as a block.
CARD_FIELDS_JS = r"""() => {
  const txt = el => (el && (el.innerText || el.textContent) || '').trim();
  const q = (root, sel) => root.querySelector(sel);
  const rows = c => [...c.querySelectorAll('.W4Efsd')].map(b => {
      const lines = txt(b).split('\n').filter(Boolean);
      return lines.length ? lines[0].trim() : '';
    });

  // (category, street) from the "category · street" row, or null.
  const pair = blocks => {
    for (const text of blocks) {
      if (!text.includes('·')) continue;
      const i = text.indexOf('·');
      const head = text.slice(0, i).trim();
      const tail = text.slice(i + 1).trim();
      const low = head.toLowerCase();
      if (head && !/^\d/.test(head) &&
          !low.startsWith('buka') && !low.startsWith('tutup') &&
          !low.startsWith('open') && !low.startsWith('closed')) {
        return [head, tail];
      }
    }
    return null;
  };

  return [...document.querySelectorAll('div[role="article"]')].map(c => {
    const a = c.querySelector('a[href*="/maps/place/"]');
    const blocks = rows(c);
    const p = pair(blocks);
    let address = p ? p[1] : null;
    if (!address) {
      for (const text of blocks) {
        if (text.length < 6) continue;
        const low = text.toLowerCase();
        if (low.startsWith('open') || low.startsWith('closed') ||
            low.startsWith('buka') || low.startsWith('tutup') ||
            low.startsWith('·')) continue;
        address = text;
        break;
      }
    }
    let status = null;
    for (const text of blocks) {
      const low = text.toLowerCase();
      if (low.includes('buka') || low.includes('open')) { status = 'Open'; break; }
      if (low.includes('tutup') || low.includes('closed')) { status = 'Closed'; break; }
    }
    const web = q(c, 'a[data-value="Website"], a.lcr4fd');
    return {
      raw_name: txt(q(c, '.fontHeadlineSmall, .qBF1Pd')) ||
                txt(c).split('\n')[0] || '',
      raw_rating: txt(q(c, '.MW4etd, .AJ710c')),
      raw_review_count: txt(q(c, '.UY7F9')),
      raw_address: address || '',
      raw_category: p ? p[0] : '',
      raw_phone: txt(q(c, '.UsdlK')),
      raw_website: web ? (web.getAttribute('href') || '').trim() : '',
      raw_maps_url: a ? a.href : null,
      raw_opening_status: status,
      href: a ? a.href : null,
    };
  });
}"""


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
        """Navigate, load results, and return one dict per result card.

        Each dict carries the card's parsed fields plus the place href, because
        the contact rows live on the place page rather than on this feed and
        the feed is navigated away from during enrichment.

        Kept browser-facing only; parsing lives in extractor/parser.
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

        # Read every field in one pass. ElementHandles would be invalidated by
        # the navigation that enrichment does, and one evaluate() keeps the
        # snapshot consistent with the hrefs read at the same instant.
        rows = await self.page.evaluate(CARD_FIELDS_JS)
        rows = [r for r in rows if r.get("href")]
        logger.info("Found %d cards for %s / %s", len(rows), keyword, location)
        return rows

    # A role="region" node carrying data-item-id="address" is the detail panel.
    # role="dialog" also matches on this page but resolves to an invisible
    # overlay, so every lookup through it comes back empty.
    PANEL = 'div[role="region"]:has([data-item-id="address"])'
    # The place URL names the business, e.g.
    # /maps/place/Sikadu+Coffee/@-7.3552981,109.3613334,13z/data=...
    # Maps updates it a beat *after* the click lands and the panel repaints,
    # so polling it is what tells us the click actually took effect. The
    # panel itself is unreliable here: it is sometimes reused rather than
    # re-created, and Escape only hides it.
    URL_PLACE = re.compile(r"/maps/place/([^/]+)")

    async def _place_slug(self) -> Optional[str]:
        """Return the business name currently encoded in the URL, or None."""
        return (self.URL_PLACE.search(self.page.url) or [None, None])[1]

    async def open_place(self, href: str, expect_name: Optional[str] = None):
        """Navigate straight to a card's place URL and return the panel handle.

        Contact rows (phone, website) only exist inside the detail panel, never
        on the feed card, so each lead needs its own page load to get them.

        Navigating to the card's href is used instead of clicking it because
        clicking is a race Maps does not resolve synchronously: it repaints the
        panel for the *previous* card first, so reading immediately after a
        click returns the previous lead's phone — one row out of step, and
        Escape hides the panel rather than removing it, so there is no signal
        to wait on. A navigation has an unambiguous target and an unambiguous
        end: the document for that place and nothing else.

        expect_name is the card's business name, used only as a cross-check
        that the loaded place is the one that was asked for.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        url = href if href.startswith("http") else "https://www.google.com" + href
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
        except Exception as exc:
            logger.debug("Navigation to %s failed: %s", href[:70], exc)
            return None

        try:
            await self.page.wait_for_selector(self.PANEL, timeout=self.timeout)
        except Exception:
            logger.debug("No detail panel at %s", href[:70])
            return None

        if expect_name:
            slug = await self._place_slug()
            if slug and not _slug_matches(slug, expect_name):
                logger.debug("Loaded %r but wanted %r", slug, expect_name)
                return None
        return await self.page.query_selector(self.PANEL)

    async def close_detail_panel(self) -> None:
        """No-op kept so callers read the same as before.

        ponytail: each lead gets its own navigation now, so there is no panel
        to dismiss. Remove this call once the collector stops speaking in
        open/close pairs.
        """

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
