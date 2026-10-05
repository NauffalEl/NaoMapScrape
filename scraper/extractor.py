"""Extractor — pull raw text fields from a Google Maps result card."""

import logging
from typing import Optional

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


async def _address(element) -> Optional[str]:
    """Address usually lives in the first W4Efsd block."""
    blocks = await element.query_selector_all(SEL["address_blocks"])
    for block in blocks:
        text = (await block.inner_text()).strip()
        # Skip rating-only, hours-only or review-count-only fragments.
        if len(text) < 6:
            continue
        low = text.lower()
        if low.startswith(("open", "closed", "buka", "tutup", "·")):
            continue
        return text
    return None


async def _opening_status(element) -> Optional[str]:
    blocks = await element.query_selector_all(SEL["address_blocks"])
    for block in blocks:
        text = (await block.inner_text()).strip().lower()
        if "open" in text or "buka" in text:
            return "Open"
        if "closed" in text or "tutup" in text:
            return "Closed"
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
                "raw_category": await _text(card, SEL["category"]),
                "raw_phone": await _text(card, SEL["phone"]),
                "raw_website": await _attr(card, SEL["website"]),
                "raw_maps_url": await _attr(card, SEL["maps_link"]),
                "raw_opening_status": await _opening_status(card),
            }
        except Exception as exc:
            logger.warning("Failed to extract card: %s", exc)
            return None

    async def extract_all(self, cards) -> list:
        """Extract every card; skips cards that fail or are not businesses."""
        results = []
        for card in cards:
            data = await self.extract_card(card)
            if data:
                results.append(data)
        return results
