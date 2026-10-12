"""End-to-end check that each lead's fields come from that lead's own place page.

The previous guard failed silently — it returned the previous lead's phone
while reporting success. So this prints the card name, the place URL slug, the
panel address and the phone side by side, and counts an empty phone or address
as a problem: a mis-timed read used to produce a MISS that looked clean
precisely because it read nothing at all.
"""
import asyncio
import re
import sys
import time
from urllib.parse import unquote_plus

sys.path.insert(0, ".")

from scraper.google_maps import GoogleMapsScraper
from scraper.extractor import _phone_from_panel

N = 12
URL_PLACE = re.compile(r"/maps/place/([^/]+)")


async def main():
    s = GoogleMapsScraper(headless=True)
    await s.start()
    try:
        rows = await s.search("kopi", "Purbalingga")
        print(f"cards={len(rows)}\n")

        t0 = time.perf_counter()
        out = []
        for i, row in enumerate(rows[:N]):
            name = (row.get("raw_name") or "")[:26]
            m = URL_PLACE.search(row.get("href") or "")
            slug = unquote_plus(m.group(1)) if m else ""
            t1 = time.perf_counter()
            panel = await s.open_place(row["href"], expect_name=row.get("raw_name"))
            t2 = time.perf_counter()

            tel, addr = "", ""
            if panel:
                tel = await _phone_from_panel(panel) or ""
                el = await panel.query_selector('[data-item-id="address"]')
                addr = ((await el.inner_text()) if el else "").replace("\ue0c8", "")
                addr = " ".join(addr.split())
            out.append((i, name, slug, tel, addr))
            print(f"[{i:2}] {t2-t1:5.2f}s {'ok  ' if tel else 'MISS'} "
                  f"{name:24} | {slug[:20]:22} | {tel or '-':13} {addr[:34]}")

        dt = time.perf_counter() - t0
        n = max(len(out), 1)
        missing = [r for r in out if not r[3] or not r[4]]

        # A duplicated address across adjacent rows is the off-by-one tell:
        # a mis-timed read returns the previous place's address.
        dup = [
            (out[i - 1][1], out[i][1], out[i][4])
            for i in range(1, len(out))
            if out[i][4] and out[i][4] == out[i - 1][4]
        ]

        print(f"\nrows={len(out)} with_phone={len(out)-len(missing)} "
              f"per_card={dt/n:.2f}s")
        print(f"rows missing phone/address: {len(missing)}")
        print(f"duplicate adjacent addresses (off-by-one): {len(dup)}")
        for d in dup:
            print("   ", d)
        assert not dup, "panel rows are misaligned"
        print("\nALIGNMENT OK")
    finally:
        await s.stop()


asyncio.run(main())