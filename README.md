# Preisvergleich Scraper

Scrapes product prices from four Austrian supermarkets and syncs them to Google Cloud Firestore.

| Supermarket | Method | Source |
|-------------|--------|--------|
| **Billa** | REST API | `billa.at` |
| **Penny** | REST API | `penny.at` |
| **Spar** | Playwright (async) | `spar.at` |
| **Hofer** | Playwright (sync) | `hofer.at` |

### Billa — API endpoints

All requests go to a single paginated endpoint (page size 500):

```
GET https://www.billa.at/api/product-discovery/categories/{category}/products
    ?sortBy=relevance&pageSize=500&page=N
```

Categories scraped:
`neu-im-online-shop`, `obst-und-gemuese`, `brot-und-gebaeck`, `fleisch-wurst-und-fisch`,
`kuehlwaren`, `schnelle-kueche`, `platten-broetchen-und-co`, `getraenke`, `vorratsschrank`,
`tiefkuehl`, `rein-pflanzlich`, `drogerie-und-kosmetik`, `kueche-haushalt-und-garten`,
`baby-und-kleinkind`, `haustier`

### Penny — API endpoints

Penny uses the same API shape as Billa. It does not scrape regular product categories —
instead it scrapes the **current weekly offer tabs** only:

1. Fetch `https://www.penny.at/angebote` to discover active tab slugs (e.g. `angebote-ab-1903`).
   Tabs older than 14 days or dated in the future are skipped.
2. For each live tab, hit the products endpoint:
   ```
   GET https://www.penny.at/api/product-discovery/categories/angebote-ab-{DDMM}/products
       ?sortBy=relevance&pageSize=500&page=N
   ```

### Spar — pages scraped

Uses Playwright (async, up to 2 concurrent browser contexts) to render category listing pages:

```
https://www.spar.at/produktwelt/{category}
```

Infinite-scroll is handled by repeatedly scrolling to the bottom. Categories defined
(some are currently commented-out for faster dev runs):
`obst-gemuese`, `brot-gebaeck`, `milchprodukte-alternativen`, `tiefkuehlprodukte`,
`wurst-fleisch-eier-fisch`, `beilagen-essig-oel-gewuerze`, `backen-fruehstueck`,
`suesses-salziges`, `schnelle-kueche-to-go`, `babynahrung`, `alkoholfreie-getraenke`,
`kaffee-tee-kakao`, `alkoholische-getraenke`

### Hofer — pages scraped

Uses Playwright (sync) and visits up to three page types:

| Page | URL |
|------|-----|
| Weekly offers index | `https://www.hofer.at/de/angebote.html` |
| Per-date offer leaflet | `https://www.hofer.at/de/angebote/d.{DD-MM-YYYY}.html` |
| Tiefpreis Aktionen | `https://www.hofer.at/de/angebote/aktionen.html` |
| Product category *(commented out)* | `https://www.hofer.at/de/sortiment/produktsortiment/{category}.html` |

The scraper starts at the offers index, extracts all date-based leaflet links whose date
is ≤ today, then visits each one to collect products.
Tiefpreis/Aktionen products are scraped from the dedicated actions page.

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
