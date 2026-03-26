# Preisvergleich Scraper

A Python scraper that collects product data (prices, promotions, unit prices, etc.) from four major Austrian supermarkets and syncs them to Google Cloud Firestore. Designed to power a price-comparison app.

## Supported Supermarkets

| Supermarket | Scraping Method | Source |
|-------------|----------------|--------|
| **Billa** | REST API (`requests`) | `billa.at` product-discovery API |
| **Spar** | Browser automation (`playwright`, async) | `spar.at` product pages |
| **Hofer** | Browser automation (`playwright`, sync) | `hofer.at` product pages |
| **Penny** | REST API (`requests`) | `penny.at` product-discovery API |

## Project Structure

```
├── main.py                 # CLI entry point – orchestrates scraping & uploading
├── firebase_store.py       # Firebase init & per-supermarket upload dispatcher
├── firestore_sync.py       # Diff-based Firestore sync (hash comparison)
├── requirements.txt        # Python dependencies
├── firebase-key.json       # Firebase service-account key (not committed)
├── scrapers/
│   ├── billa.py            # Billa scraper (REST API)
│   ├── spar.py             # Spar scraper (Playwright, async)
│   ├── hofer.py            # Hofer scraper (Playwright, sync)
│   └── penny.py            # Penny scraper (REST API)
├── tests/                  # Unit tests (pytest)
└── screenshots/            # Debug screenshots from Playwright on failure
```

## Setup

### Prerequisites

- Python 3.10+
- A Firebase project with Firestore enabled (for uploading)

### Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

### Firebase Credentials

Provide credentials in one of two ways:

1. **Environment variable** – set `FIREBASE_KEY` to the full JSON string of your service-account key.
2. **Local file** – place a `firebase-key.json` file in the project root.

If neither is found, scraping still works but uploading is skipped.

## Usage

```bash
# Scrape all supermarkets and upload to Firestore
python main.py

# Scrape only (skip Firestore upload)
python main.py --no-upload

# Upload previously scraped JSON files without re-scraping
python main.py --upload-only
```

Each scraper writes its results to a local JSON file (`billa.json`, `spar.json`, `hofer.json`, `penny.json`) before uploading.

## How the Scrapers Work

All scrapers produce a list of product dicts with a common schema:

```json
{
  "id": "billa_00-123456",
  "name": "Bio-Vollmilch",
  "price": 1.49,
  "originalPrice": 1.99,
  "promotionText": "-25%",
  "unitPrice": 1.49,
  "unitLabel": "l",
  "category": "kuehlwaren-15416",
  "brand": "Ja! Natürlich",
  "sku": "00-123456",
  "inPromotion": true,
  "imageUrl": "https://...",
  "supermarket": "billa"
}
```

### Billa (`scrapers/billa.py`)

Uses the **Billa REST API** directly. Iterates over a predefined list of category slugs, fetching paginated product data (page size 500). Each API response returns structured JSON with price, brand, and promotion fields that are mapped to the common schema. No browser automation needed.

**Flow:** category list → paginated GET requests → parse JSON → write `billa.json`

### Penny (`scrapers/penny.py`)

Also uses a **REST API** (same structure as Billa). In addition to regular categories, it scrapes **live offer tabs**: it fetches the offers HTML page, extracts tab slugs with dates (e.g. `angebote-ab-1903`), filters to currently active tabs (date ≤ today, not older than 14 days), and scrapes those via the same API.

**Flow:** fetch offer tab dates → filter live tabs → paginated GET requests per tab → parse JSON → write `penny.json`

### Spar (`scrapers/spar.py`)

Uses **Playwright (async)** to render Spar's JavaScript-heavy product listing pages. For each category, it navigates to the page, dismisses cookie banners, reads the total page count from the pagination widget ("1 von 11"), then iterates through every page. Product data is extracted from DOM elements (`article.product-tile`). Categories are scraped concurrently with a semaphore limiting parallelism to 2 browser contexts.

**Flow:** launch headless Chromium → scrape categories concurrently (max 2) → paginate through pages → parse DOM tiles → write `spar.json`

#### Spar Product ID Strategy

Each product needs a stable `id` used as the Firestore document key. The Spar scraper uses a two-tier approach:

1. **Primary: SKU from URL** – The scraper extracts a numeric SKU from the product link href (e.g. `/produktwelt/...-p2020003543821` → `2020003543821`) or the image URL (e.g. `.../at/2020003543821/HB_500px.jpg`). The link href is preferred because it is always present in the initial HTML, while image `src` attributes can be lazy-loaded placeholders. The resulting ID has the format `spar_<sku>`.

2. **Fallback: Deterministic hash** – If neither URL yields a SKU (rare), a stable ID is generated from an MD5 hash of `brand|name|category` (lowercased, truncated to 12 hex chars). The resulting ID has the format `spar_hash_<hash>`.

**Why SKU over hash for all products?** The SKU is tied to Spar's internal product system, so it survives minor name/branding text changes that would break a hash. It also enables cross-referencing with other data sources. The hash fallback only covers the small percentage of products where SKU extraction fails, ensuring no product ever gets a `null` ID.

**Deduplication across runs:** The diff-based Firestore sync (see below) automatically handles the case where a product transitions from a hash-based ID to a SKU-based ID between runs. The old `spar_hash_*` document is detected as "removed" and deleted, while the new `spar_<sku>` document is written as "new". No manual cleanup is needed.

The scraper logs the number of null-SKU products per category and in the final summary for monitoring.

### Hofer (`scrapers/hofer.py`)

Uses **Playwright (sync)** to scrape Hofer's product pages. For regular categories, it navigates to each page and clicks the "Mehr anzeigen" (show more) button repeatedly until all products are loaded. It also scrapes **date-based offer pages**: it loads the offers page, extracts date links (e.g. `/de/angebote/d.23-03-2026.html`), filters to current/past dates, and scrapes each one. Products from offers are marked with `inPromotion: true`. SKU-based deduplication removes products that appear in multiple categories.

**Flow:** launch headless Chromium → scrape categories (click "show more" to load all) → scrape offer date pages → deduplicate by SKU → write `hofer.json`

### Error Handling & Debugging

- Playwright scrapers save **screenshots** to `screenshots/` on failure for CI debugging.
- Spar retries pages up to 5 times if the search returns an error ("Leider funktioniert unsere Suche").
- All scrapers catch per-category errors so a single failure doesn't abort the entire run.

## How Firestore Storage Works

The upload pipeline is split into two modules:

### `firebase_store.py` – Initialization & Dispatch

1. **Initializes Firebase Admin SDK** using either the `FIREBASE_KEY` environment variable (JSON string) or a local `firebase-key.json` file.
2. Each supermarket's products go into their **own Firestore collection** named `<supermarket>_products` (e.g. `billa_products`, `spar_products`).
3. Delegates the actual write logic to `firestore_sync.py`.

### `firestore_sync.py` – Diff-Based Sync

Instead of deleting all documents and re-writing them on every run, this module uses a **hash-based diff** to minimise Firestore read/write/delete operations (important for quota and cost):

1. **Read metadata** – A single document in the `_sync_metadata` collection stores an MD5 hash for every product ID in that supermarket's collection.
2. **Compute new hashes** – Each scraped product is serialized to deterministic JSON and hashed with MD5.
3. **Diff** – Compare old hashes vs. new hashes to determine:
   - **New / changed** products → write (set) to Firestore
   - **Removed** products → delete from Firestore
   - **Unchanged** products → skip entirely
4. **Batched writes** – Writes and deletes are performed in Firestore batches of up to 500 operations (the Firestore limit) with exponential back-off retry on failures and a 1.5 s cooldown between batches.
5. **Persist hashes** – After committing all changes, the metadata document is updated with the new hash map.

This approach means that if product data hasn't changed between runs, **zero product documents are written**, keeping Firestore costs minimal.

## Running Tests

```bash
pytest tests/ -v
```

## Dependencies

- `requests` – HTTP client for API-based scrapers (Billa, Penny)
- `playwright` – headless browser automation for DOM-based scrapers (Spar, Hofer)
- `firebase-admin` – Google Firebase Admin SDK for Firestore access
- `pytest` – test runner
