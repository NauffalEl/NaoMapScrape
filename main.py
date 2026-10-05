"""NaoMapScrape — Main Entry Point."""

import argparse
import asyncio
import logging
import os
import sys

from core.collector import Collector
from cli.interface import CLIInterface, welcome
from export.csv_exporter import export_csv

# Configure logging to file only to keep CLI clean
os.makedirs("data/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler("data/logs/scraper.log", encoding="utf-8")],
)
logger = logging.getLogger("naomapscrape")


async def main():
    parser = argparse.ArgumentParser(description="NaoMapScrape — Google Maps Lead Scraper")
    parser.add_argument("keywords", help="Keywords (comma separated)")
    parser.add_argument("--locations", "-l", help="Locations (comma separated)", required=True)
    parser.add_argument("--limit", type=int, default=50, help="Max leads to collect")
    parser.add_argument("--filter", choices=["ALL", "HAS_WEBSITE", "NO_WEBSITE"], default="ALL", help="Website filter")
    parser.add_argument("--export", default="data/exports/leads.csv", help="Export path")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--gui", action="store_false", dest="headless", help="Show browser window")
    
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")]
    locations = [l.strip() for l in args.locations.split(",")]

    cli = CLIInterface()
    
    def on_progress(payload):
        cli.update(payload)

    collector = Collector(
        headless=args.headless,
        on_progress=on_progress
    )

    cli.start(args.limit)
    try:
        leads = await collector.run(
            keywords=keywords,
            locations=locations,
            limit=args.limit,
            website_filter=args.filter
        )
        
        cli.stop()
        cli.show_results(leads)
        
        if leads:
            export_csv(leads, args.export)
            print(f"\nSaved {len(leads)} leads to {args.export}")
            
    except KeyboardInterrupt:
        print("\nStopping gracefully...")
        collector.stop()
    except Exception as e:
        logger.exception("Fatal error")
        print(f"\nError: {e}")
    finally:
        collector.db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
