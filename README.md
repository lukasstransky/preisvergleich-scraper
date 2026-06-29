# Preisvergleich Scraper

Scrapes product prices from Austrian supermarkets and syncs them to Google Cloud Firestore.

| Supermarket | Was wird gescraped | Angebote erkannt? | Methode |
|-------------|-------------------|:-----------------:|---------|
| **Billa** | Alle Produktkategorien | ✓ (via API-Flag) | REST API |
| **Penny** | Nur aktuelle Wochenangebote | ✓ (immer) | REST API |
| **Lidl** | Nur aktuelle Aktionsprodukte | ✓ (immer) | REST API |
| **SPAR** | Alle Produktkategorien | ✓ (via DOM) | Playwright (async) |
| **Hofer** | Nur Angebotsflugblätter + Tiefpreis-Aktionen | ✓ (immer) | Playwright (sync) |
| **MPreis** | Lebensmittel, Getränke + Aktionsseite | ✓ (via DOM) | Playwright (async) |

> **Penny** und **Lidl** scrapen ausschließlich Angebote — alle Produkte haben `inPromotion: true`.
> **Billa**, **SPAR** und **MPreis** scrapen das gesamte Sortiment und erkennen Angebote aus der Seite.
> **Hofer** scraped nur Flugblätter, kein reguläres Sortiment.

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

### Lidl — API endpoints

Scraped via a single paginated API endpoint. Only the promotional "Essen & Trinken" category is scraped — all returned products are current in-store offers. The API returns `storeStartDate`/`storeEndDate` as Unix timestamps which are converted to `YYYY-MM-DD`.

```
GET https://www.lidl.at/p/api/restaurant/products
    ?categoryId=10068374&language=de&country=AT&offset=N&limit=24
```

### SPAR — pages scraped

Uses Playwright (async, up to 2 concurrent browser contexts) to render category listing pages:

```
https://www.spar.at/produktwelt/{category}
```

Promotion detection happens via DOM: `span.product-price__price-old` for the crossed-out original price and `div.product-price__promo-pill` for the badge text (e.g. "Aktion!", "Immer billig!", "Mengenvorteil ab 2 Stk.").

Categories scraped:
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

### MPreis — pages scraped

Uses Playwright (async) to render three category pages:

```
https://www.mpreis.at/shop/c/lebensmittel
https://www.mpreis.at/shop/c/getraenke
https://www.mpreis.at/shop/c/aktionen/aktuell
```

Products from the `aktionen` page get `inPromotion: true` automatically. For all pages, promotion detection also happens via DOM (strike-through price, discount badge).

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
python main.py --scraper spar --no-upload --spar-categories obst-gemuese milch-kaeseprodukte
```

Available SPAR categories: `obst-gemuese`, `brot-gebaeck`, `milchprodukte-alternativen`, `tiefkuehlprodukte`,
`wurst-fleisch-eier-fisch`, `beilagen-essig-oel-gewuerze`, `backen-fruehstueck`, `suesses-salziges`,
`schnelle-kueche-to-go`, `babynahrung`, `alkoholfreie-getraenke`, `kaffee-tee-kakao`, `alkoholische-getraenke`

To deactivate the virtual environment when done: `deactivate`

## Documentation

- [docs/scrapers.md](docs/scrapers.md) – how each scraper works, product schema, ID strategies
- [docs/fields-by-scraper.md](docs/fields-by-scraper.md) – which fields are populated by which scraper
- [docs/firestore.md](docs/firestore.md) – diff-based sync, data layout, resumability, quota impact
- [docs/testing.md](docs/testing.md) – running tests, integration test overview, data quality analysis
