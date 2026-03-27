# Preisvergleich Scraper

Scrapes product prices from four Austrian supermarkets and syncs them to Google Cloud Firestore.

| Supermarket | Method | Source |
|-------------|--------|--------|
| **Billa** | REST API | `billa.at` |
| **Penny** | REST API | `penny.at` |
| **Spar** | Playwright (async) | `spar.at` |
| **Hofer** | Playwright (sync) | `hofer.at` |

## Setup

**Requirements:** Python 3.10+, a Firebase project with Firestore enabled.

```bash
pip install -r requirements.txt
playwright install chromium
```

**Firebase credentials** – provide one of:
- `FIREBASE_KEY` env var containing the service-account JSON string
- `firebase-key.json` file in the project root

If neither is found, scraping still works but uploading is skipped.

## Usage

```bash
python main.py               # scrape all + upload to Firestore
python main.py --no-upload   # scrape only, skip upload
python main.py --upload-only # upload existing *.json files without re-scraping
```

## Documentation

- [docs/scrapers.md](docs/scrapers.md) – how each scraper works, product schema, ID strategies
- [docs/firestore.md](docs/firestore.md) – diff-based sync, data layout, resumability, quota impact
- [docs/testing.md](docs/testing.md) – running tests, integration test overview, data quality analysis
