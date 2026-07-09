# Preisvergleich Scraper

Scrapes product prices from Austrian supermarkets and syncs them to Google Cloud Firestore.

| Supermarket | Was wird gescraped | Angebote erkannt? | Methode |
|-------------|-------------------|:-----------------:|---------|
| **Billa** | Alle Produktkategorien | ✓ (via API-Flag) | REST API |
| **Penny** | Nur aktuelle Wochenangebote | ✓ (immer) | REST API |
| **Lidl** | Nur aktuelle Aktionsprodukte | ✓ (immer) | REST API |
| **SPAR** | Alle Produktkategorien | ✓ (via DOM) | Playwright (async) |
| **Hofer** | Produktsortiment + Angebotsflugblätter + Tiefpreis-Aktionen | ✓ (via DOM + immer) | Playwright (sync) |
| **MPreis** | Lebensmittel, Getränke + Aktionsseite | ✓ (via DOM) | Playwright (sync) |

> **Penny** und **Lidl** scrapen ausschließlich Angebote — alle Produkte haben `inPromotion: true`.
> **Billa**, **SPAR**, **Hofer** und **MPreis** scrapen das reguläre Sortiment und erkennen Angebote aus der Seite.
> Bei **Hofer** kommen zusätzlich die Angebotsflugblätter und Tiefpreis-Aktionen dazu (dort ist `inPromotion` immer `true`).

### Billa — API endpoints

All requests go to a single paginated endpoint (page size 500):

```
GET https://www.billa.at/api/product-discovery/categories/{category}/products
    ?sortBy=relevance&enableStatistics=false&enablePersonalization=false&pageSize=500&page=N
```

`inPromotion` comes straight from the API's own flag on each product.

Categories scraped (the slugs include a numeric category ID):
`neu-im-online-shop-14506`, `obst-und-gemuese-13751`, `brot-und-gebaeck-15520`,
`fleisch-wurst-und-fisch-15388`, `kuehlwaren-15416`, `schnelle-kueche-15389`,
`platten-broetchen-und-co-15409`, `getraenke-13784`, `vorratsschrank-15012`,
`tiefkuehl-15415`, `rein-pflanzlich-15207`, `drogerie-und-kosmetik-15274`,
`kueche-haushalt-und-garten-15320`, `baby-und-kleinkind-15671`, `haustier-15672`

### Penny — API endpoints

Penny uses the same API shape as Billa. It does not scrape regular product categories —
instead it scrapes the aggregate **"Alle Angebote"** category, which rolls up every offer
tab (current week, upcoming weeks, and themed tabs like "Wochenstarter"):

1. Hit the products endpoint on the aggregate category, paginated:
   ```
   GET https://www.penny.at/api/product-discovery/categories/alle-angebote-99000000/products
       ?sortBy=relevance&enableStatistics=false&enablePersonalization=false&pageSize=500&page=N
   ```
2. Drop products whose offer has expired (per-product `validityEnd < today`); keep
   currently-valid and upcoming ones. All are forced to `inPromotion: true`.

This is more complete than the old approach of parsing individual dated tab slugs
(e.g. `angebote-ab-1903`) out of the offers HTML — that missed themed and upcoming tabs.

### Lidl — API endpoints

Scraped via a single paginated search API endpoint. Only the "Essen & Trinken" category (`category.id=10068374`) is scraped — every product on this page is an in-store promotion ("Angebote in deiner Filiale"), so `inPromotion` is always `true`. The API returns `storeStartDate`/`storeEndDate` as Unix timestamps which are converted to `YYYY-MM-DD`. Pagination follows `numFound` with a page size of 500.

```
GET https://www.lidl.at/q/api/search
    ?assortment=AT&locale=de_AT&version=v2.0.0&sort=relevancy
    &category.id=10068374&offset=N&limit=500
```

Some products are Lidl-Plus-only (no regular `price`); the parser falls back to the `lidlPlus` price array for those.

### SPAR — pages scraped

Uses Playwright (async, up to 2 concurrent browser contexts) to render category listing pages:

```
https://www.spar.at/produktwelt/{category}
```

Promotion detection happens via DOM: `span.product-price__price-old` for the crossed-out original price and `div.product-price__promo-pill` for the badge text (e.g. "Aktion!", "Immer billig!", "Mengenvorteil ab 2 Stk.").

Categories scraped:
`obst-gemuese`, `brot-gebaeck`, `milchprodukte-alternativen`, `tiefkuehlprodukte`,
`wurst-fleisch-eier-fisch`, `beilagen-essig-oel-gewuerze`, `backen-fruehstueck`,
`suesses-salziges`, `schnelle-kueche-to-go`, `alkoholfreie-getraenke`,
`kaffee-tee-kakao`, `alkoholische-getraenke` (`babynahrung` is currently commented out)

### Hofer — pages scraped

Uses Playwright (sync) and visits three page types:

| Page | URL |
|------|-----|
| Product category | `https://www.hofer.at/de/sortiment/produktsortiment/{category}.html` |
| Weekly offers index | `https://www.hofer.at/de/angebote.html` |
| Per-date offer leaflet | `https://www.hofer.at/de/angebote/d.{DD-MM-YYYY}.html` |
| Tiefpreis Aktionen | `https://www.hofer.at/de/angebote/aktionen.html` |

The scraper runs three passes and merges the results (deduplicated by SKU):

1. **Regular product categories** — each category listing is loaded and "Mehr anzeigen"
   is clicked until all tiles are visible. Products only get `inPromotion: true` here when
   the tile shows a crossed-out original price (`.price_before del`).
2. **Weekly offers** — starts at the offers index, extracts all date-based leaflet links
   whose date is ≤ today, then visits each one. All products are marked `inPromotion: true`
   with `promotionText: "ab {DD.MM.YYYY}"` and an `offerStart` date.
3. **Tiefpreis Aktionen** — scraped from the dedicated actions page; all products are
   marked `inPromotion: true` with `promotionText: "Tiefpreis Aktion"`.

Categories scraped:
`brot-und-backwaren`, `fleisch-und-fisch`, `getraenke`, `kuehlung`, `vorratsschrank`,
`tiefkuehlung`, `suesses-und-salziges` (`drogerie` is currently commented out).

### MPreis — pages scraped

Uses Playwright (sync) to render three pages, clicking "Mehr laden" until all tiles are loaded:

```
https://www.mpreis.at/shop/c/lebensmittel-50234186
https://www.mpreis.at/shop/c/getraenke-13743475
https://www.mpreis.at/aktionen/aktuell/alle-produkte-in-aktion
```

Products from the `aktionen` page get `inPromotion: true` automatically. For all pages, promotion detection also happens via DOM (strike-through price, discount badge, screen-reader "statt"-price, multi-buy promo text). Products appearing on multiple pages are deduplicated by SKU.

## Setup

**Requirements:** Python 3.10+, a Firebase project with Firestore enabled.

```bash
# Create virtual environment (once)
python3 -m venv venv

# Activate it (every new terminal session)
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

**Firebase credentials** – provide one of:
- `FIREBASE_KEY` env var containing the service-account JSON string
- `firebase-key.json` file in the project root

If neither is found, scraping still works but uploading is skipped.

## Usage

Make sure the virtual environment is active (`source venv/bin/activate`) before running any command.

```bash
python main.py               # scrape all + upload to Firestore
python main.py --no-upload   # scrape only, skip upload
python main.py --upload-only # upload existing *.json files without re-scraping
```

| | JSON updated | Firestore sync | Price history |
|---|:---:|:---:|:---:|
| `python main.py` | ✓ | ✓ | ✓ |
| `python main.py --no-upload` | ✓ | ✗ | ✗ |
| `python main.py --upload-only` | ✗ | ✓ | ✓ |

Price history entries (`products/{id}/price_history/{date}`) are only written during a Firestore upload.

### Partial runs

Run only specific scrapers with `--scraper`:

```bash
python main.py --scraper spar --no-upload
python main.py --scraper billa penny --no-upload
```

For SPAR, limit to specific categories with `--spar-categories` (useful for quick testing):

```bash
python main.py --scraper spar --no-upload --spar-categories obst-gemuese
python main.py --scraper spar --no-upload --spar-categories obst-gemuese milchprodukte-alternativen
```

Available SPAR categories: `obst-gemuese`, `brot-gebaeck`, `milchprodukte-alternativen`, `tiefkuehlprodukte`,
`wurst-fleisch-eier-fisch`, `beilagen-essig-oel-gewuerze`, `backen-fruehstueck`, `suesses-salziges`,
`schnelle-kueche-to-go`, `alkoholfreie-getraenke`, `kaffee-tee-kakao`, `alkoholische-getraenke`

To deactivate the virtual environment when done: `deactivate`

## Documentation

- [docs/scrapers.md](docs/scrapers.md) – how each scraper works, product schema, ID strategies
- [docs/fields-by-scraper.md](docs/fields-by-scraper.md) – which fields are populated by which scraper
- [docs/firestore.md](docs/firestore.md) – diff-based sync, data layout, resumability, quota impact
- [docs/testing.md](docs/testing.md) – running tests, integration test overview, data quality analysis
