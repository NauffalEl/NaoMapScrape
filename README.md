# NaoMapScrape CLI

Google Maps Lead Discovery CLI Tool.

## Installation

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Run the tool:
   ```bash
   python main.py "bengkel mobil" --locations "Purwokerto, Sokaraja" --limit 100
   ```

## Features

- **Multi-Location Search**: Query multiple locations in one run.
- **Website Filtering**: Filter leads that have or lack websites.
- **Deduplication**: Automatically removes duplicate leads across runs.
- **SQLite Storage**: Persistent storage of all collected leads.
- **CSV Export**: Auto-export results for use in Excel/Google Sheets.
- **Rich Interface**: Real-time terminal progress reporting.
