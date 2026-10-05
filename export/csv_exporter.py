"""CSV and Excel exporters."""

import csv
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


def export_csv(leads: List[dict], path: str) -> None:
    """Export leads to a CSV file."""
    if not leads:
        logger.warning("No leads to export to CSV")
        return

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    keys = leads[0].keys()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(leads)
    logger.info("Exported %d leads to %s", len(leads), path)


def export_excel(leads: List[dict], path: str) -> None:
    """Export leads to an Excel file using pandas."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas not installed; skipping Excel export")
        return

    if not leads:
        logger.warning("No leads to export to Excel")
        return

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df = pd.DataFrame(leads)
    df.to_excel(path, index=False)
    logger.info("Exported %d leads to %s", len(leads), path)
