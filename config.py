"""NaoMapScrape Configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

# Project Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# Database
DB_PATH = os.path.join(DATA_DIR, "naomapscrape.db")

# Browser Settings
HEADLESS = True
BROWSER_TIMEOUT = 30000  # ms
SCROLL_PAUSE = 1.2       # seconds

# Export Defaults
DEFAULT_CSV_EXPORT = os.path.join(EXPORT_DIR, "leads.csv")
DEFAULT_EXCEL_EXPORT = os.path.join(EXPORT_DIR, "leads.xlsx")
