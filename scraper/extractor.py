"""Extractor — pull raw text fields from a Google Maps result card."""

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Selectors are centralised: Google Maps markup changes often, so edits
# only ever need to happen here.
SEL = {
    "name": ".fontHeadlineSmall, .qBF1Pd",
    "rating": ".MW4etd, .AJ710c",
    "review_count": ".UY7F9",
    "address_blocks": ".W4Efsd",
    "category": ".DkEaL, .W4Efsd:nth-child(2) > span:first-child",
    "phone": ".UsdlK",
    "website": 'a[data-value="Website"], a.lcr4fd',
    "maps_link": 'a[href*="maps/place"]',
}


async def _text(element, selector: str) -> Optional[str]:
    """Return trimmed inner text of the first match, or None."""
    el = await element.query_selector(selector)
    if not el:
        return None
    try:
        value = await el.inner_text()
    except Exception:
        return None
    return value.strip() or None


async def _attr(element, selector: str, attr: str = "href") -> Optional[str]:
    """Return an attribute of the first match, or None."""
    el = await element.query_selector(selector)
    if not el:
        return None
    value = await el.get_attribute(attr)
    return value.strip() if value else None


async def _row_pair(element) -> Optional[tuple]:
    """Return (category, street) from the card's "category · street" row.

    Google packs both into one W4Efsd div; sibling W4Efsd divs hold the
    rating and the opening hours, which is why naive block scanning used to
    return hours or "4,7(50) · Rp 1-25.000" as the address.
    """
    for block in await element.query_selector_all(SEL["address_blocks"]):
        # Some cards wrap to a second line ("Kafe\nBuka · Tutup pukul 22.00"),
        # so only the first line belongs to the category/street row.
        text = (await block.inner_text()).strip().splitlines()
        if not text:
            continue
        text = text[0].strip()
        if "·" not in text:
            continue
        head, _, tail = text.partition("·")
        head, tail = head.strip(), tail.strip()
        # A real category is words; the rating and price rows start with a digit.
        if head and not head[0].isdigit() and not head.lower().startswith(
            ("buka", "tutup", "open", "closed")
        ):
            return head, tail
    return None


async def _address(element) -> Optional[str]:
    """Street address: the tail half of the card's "category · street" row."""
    pair = await _row_pair(element)
    if pair:
        return pair[1] or None

    for block in await element.query_selector_all(SEL["address_blocks"]):
        text = (await block.inner_text()).strip()
        if len(text) < 6:
            continue
        low = text.lower()
        if low.startswith(("open", "closed", "buka", "tutup", "·")):
            continue
        return text
    return None


async def _category(element) -> Optional[str]:
    """Business category, e.g. "Kedai Kopi" or "Kafe"."""
    pair = await _row_pair(element)
    return pair[0] if pair else None


async def _opening_status(element) -> Optional[str]:
    blocks = await element.query_selector_all(SEL["address_blocks"])
    for block in blocks:
        text = (await block.inner_text()).strip().lower()
        if "open" in text or "buka" in text:
            return "Open"
        if "closed" in text or "tutup" in text:
            return "Closed"
    return None


async def _phone_from_panel(panel) -> Optional[str]:
    """Detail panel: tel link is an <a href="tel:...">, sometimes a
    data-item-id="phone:tel:..." button. Either shape is accepted."""
    # Anchor form is what Google currently renders.
    el = await panel.query_selector('a[href^="tel:"]')
    if el:
        href = await el.get_attribute("href")
        tel = (href or "").split("tel:", 1)[-1].strip()
        if tel:
            return tel

    for sel in (
        '[data-item-id^="phone:tel:"]',
        'button[aria-label*="Telepon"]',
        'button[aria-label*="Phone"]',
    ):
        el = await panel.query_selector(sel)
        if not el:
            continue
        value = await el.get_attribute("data-item-id")
        if value:
            tel = value.split("tel:", 1)[-1].strip()
            if tel:
                return tel
        label = await el.get_attribute("aria-label") or ""
        m = re.search(r"([+\d][\d\s\-()]{6,})", label)
        if m:
            return m.group(1).strip()
    return None


async def _website_from_panel(panel) -> Optional[str]:
    """Detail panel: website is a button with data-item-id 'authority' or an
    <a> whose href leaves Google. CsEnBe is the truncated link label."""
    for sel in (
        'button[data-item-id="authority"]',
        'a[data-item-id="authority"]',
        'button[data-item-id^="website"]',
        'a[data-item-id^="website"]',
    ):
        el = await panel.query_selector(sel)
        if not el:
            continue
        href = await el.get_attribute("href")
        if href and href.startswith("http") and "google." not in href:
            return href.strip()
        label = await el.get_attribute("aria-label")
        if label and "." in label:
            return label.strip()

    # Fallback: the website link inside the CsEnBe row.
    for sel in ("a.CsEnBe", "div.CsEnBe a", 'a[data-value="Website"]'):
        el = await panel.query_selector(sel)
        if not el:
            continue
        href = await el.get_attribute("href")
        if href and href.startswith("http") and "google." not in href:
            return href.strip()
    return None


class Extractor:
    """Reads raw string fields from a single card element."""

    async def extract_card(self, card) -> Optional[dict]:
        """Extract raw fields from one result card. None if not a business."""
        try:
            name = await _text(card, SEL["name"])
            if not name:
                return None

            return {
                "raw_name": name,
                "raw_rating": await _text(card, SEL["rating"]),
                "raw_review_count": await _text(card, SEL["review_count"]),
                "raw_address": await _address(card),
                "raw_category": await _category(card),
                "raw_phone": await _text(card, SEL["phone"]),
                "raw_website": await _attr(card, SEL["website"]),
                "raw_maps_url": await _attr(card, SEL["maps_link"]),
                "raw_opening_status": await _opening_status(card),
            }
        except Exception as exc:
            logger.warning("Failed to extract card: %s", exc)
            return None

    async def extract_detail(self, panel, base: dict) -> dict:
        """Enrich a lead from the clicked detail panel.

        Card markup stopped rendering contact rows, so the panel is the only
        source for phone and website. It is also the reliable source for
        address: the feed card crams category, street, hours and price range
        into one W4Efsd blob, which is why card-level address parsing picks up
        "4,7(50) · Rp 1-25.000" as a street. The panel renders each field on
        its own data-item-id row, so these overwrite the card values.

        Falls back silently: missing rows simply leave the card value intact.
        """
        if not panel:
            return base
        try:
            addr = await _text(panel, '[data-item-id="address"]')
            if addr:
                base["raw_address"] = addr

            phone = await _phone_from_panel(panel)
            if phone:
                base["raw_phone"] = phone
            website = await _website_from_panel(panel)
            if website:
                base["raw_website"] = website
        except Exception as exc:
            logger.warning("Failed to extract detail panel: %s", exc)
        return base

    async def extract_all(self, cards) -> list:
        """Extract every card; skips cards that fail or are not businesses."""
        results = []
        for card in cards:
            data = await self.extract_card(card)
            if data:
                results.append(data)
        return results
