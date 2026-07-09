# Scrapers

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
  "supermarket": "billa",
  "nameTokens": ["bio", "vollmilch"],
  "normalizedCategory": "Milchprodukte"
}
```

### `nameTokens` field

Every product includes a `nameTokens` list – lowercase, deduplicated word tokens
extracted from the product name.  This field is designed for Algolia (or any
full-text search backend) to enable **word-boundary matching** instead of
substring-contains filtering.

**Why?**  A simple contains-filter for "milch" matches both "Milch 3.5%" and
"Milchschokolade".  With `nameTokens`, Algolia can match on exact tokens:
- `"Milch 3.5% 1L"` → `["milch"]` ✅ matches "milch"
- `"Milchschokolade Vollmilch 100g"` → `["milchschokolade", "vollmilch", "100g"]` ❌ no exact "milch" token

The tokenizer lives in `scrapers/tokenizer.py` and:
1. Lowercases the name
2. Splits on non-alphanumeric boundaries (keeps German umlauts ä ö ü ß)
3. Drops tokens shorter than 2 characters
4. Deduplicates while preserving order

### `normalizedCategory` field

Every product includes a `normalizedCategory` string that maps the supermarket-specific
raw `category` to one of 15 unified categories.  This enables a consistent category
filter in the Flutter app across all supermarkets.

The mapper lives in `scrapers/categories.py` and uses a two-tier strategy:
1. **Exact-match dict** for all known raw categories (~490 entries)
2. **Keyword fallback** for unknown/future categories (substring matching)
3. Falls back to `"Sonstiges"` if nothing matches

**Normalized categories:**
`Obst & Gemüse`, `Brot & Gebäck`, `Milchprodukte`, `Fleisch & Fisch`,
`Tiefkühl`, `Getränke`, `Süßes & Snacks`, `Kaffee & Tee`,
`Grundnahrungsmittel`, `Fertiggerichte`, `Frühstück & Aufstriche`,
`Alkohol`, `Drogerie & Haushalt`, `Baby & Tier`, `Sonstiges`
```

Each scraper writes its results to a local JSON file (`billa.json`, `penny.json`, `lidl.json`, `spar.json`, `hofer.json`, `mpreis.json`) before uploading.

## Billa (`scrapers/billa.py`)

Uses the **Billa REST API** directly. Iterates over a predefined list of category slugs, fetching paginated product data (page size 500). Each API response returns structured JSON with price, brand, and promotion fields that are mapped to the common schema. No browser automation needed.

**Flow:** category list → paginated GET requests → parse JSON → write `billa.json`

## Penny (`scrapers/penny.py`)

Uses a **REST API** (same structure as Billa). It scrapes **only offers**, via the aggregate `alle-angebote-99000000` ("Alle Angebote") category — this rolls up every offer tab (current week, upcoming weeks, and themed tabs like "Wochenstarter"), so it is far more complete and more robust than parsing individual dated tab slugs (e.g. `angebote-ab-1903`) out of the offers HTML. Each product carries its own `validityStart`/`validityEnd`; expired offers (`offerEnd < today`) are dropped, currently-valid and upcoming ones are kept, and all get `inPromotion: true`.

**Flow:** paginated GET requests on `alle-angebote-99000000` → parse JSON → drop expired by per-product `offerEnd` → write `penny.json`

## Spar (`scrapers/spar.py`)

Uses **Playwright (async)** to render Spar's JavaScript-heavy product listing pages. For each category, it navigates to the page, dismisses cookie banners, reads the total page count from the pagination widget ("1 von 11"), then iterates through every page. Product data is extracted from DOM elements (`article.product-tile`). Categories are scraped concurrently with a semaphore limiting parallelism to 2 browser contexts.

**Flow:** launch headless Chromium → scrape categories concurrently (max 2) → paginate through pages → parse DOM tiles → write `spar.json`

### Spar Product ID Strategy

Each product needs a stable `id` used as the Firestore document key. The Spar scraper uses a two-tier approach:

1. **Primary: SKU from URL** – The scraper extracts a numeric SKU from the product link href (e.g. `/produktwelt/...-p2020003543821` → `2020003543821`) or the image URL (e.g. `.../at/2020003543821/HB_500px.jpg`). The link href is preferred because it is always present in the initial HTML, while image `src` attributes can be lazy-loaded placeholders. The resulting ID has the format `spar_<sku>`.

2. **Fallback: Deterministic hash** – If neither URL yields a SKU (rare), a stable ID is generated from an MD5 hash of `brand|name|category` (lowercased, truncated to 12 hex chars). The resulting ID has the format `spar_hash_<hash>`.

**Why SKU over hash for all products?** The SKU is tied to Spar's internal product system, so it survives minor name/branding text changes that would break a hash. It also enables cross-referencing with other data sources. The hash fallback only covers the small percentage of products where SKU extraction fails, ensuring no product ever gets a `null` ID.

**Deduplication across runs:** The diff-based Firestore sync automatically handles the case where a product transitions from a hash-based ID to a SKU-based ID between runs. The old `spar_hash_*` document is detected as "removed" and deleted, while the new `spar_<sku>` document is written as "new". No manual cleanup is needed.

The scraper logs the number of null-SKU products per category and in the final summary for monitoring.

## Lidl (`scrapers/lidl.py`)

Uses Lidl's internal **search API** (`/q/api/search`) to fetch the single "Essen & Trinken" category (`category.id=10068374`), paginated by `numFound` with a page size of 500. Every product on this page is an in-store promotion, so `inPromotion` is always `true`. Lidl-Plus-only products (no regular `price`) fall back to their `lidlPlus` price array. No browser automation is needed.

**Flow:** paginated GET requests (single category) → parse JSON → write `lidl.json`

## Hofer (`scrapers/hofer.py`)

Uses **Playwright (sync)** to scrape Hofer's product pages in three passes:

1. **Regular categories** – navigates to each category listing and clicks the "Mehr anzeigen" (show more) button repeatedly until all products are loaded. Products are only marked `inPromotion: true` here when the tile shows a crossed-out original price.
2. **Date-based offer pages** – loads the offers index, extracts date links (e.g. `/de/angebote/d.23-03-2026.html`), filters to current/past dates, and scrapes each one. All products get `inPromotion: true` and `promotionText: "ab {date}"`.
3. **Tiefpreis Aktionen** – scrapes the dedicated actions page; all products get `inPromotion: true` and `promotionText: "Tiefpreis Aktion"`.

SKU-based deduplication removes products that appear in more than one pass.

**Flow:** launch headless Chromium → scrape categories (click "show more" to load all) → scrape offer date pages → scrape Tiefpreis Aktionen → deduplicate by SKU → write `hofer.json`

## Hofer Flugblatt (`scrapers/hofer_flugblatt.py`)

The Hofer online API only covers the orderable online assortment. The weekly in-store *Aktionen* live only in the printed leaflet, published as a **Publitas flipbook** at `https://katalog.hofer.at/`. That flipbook has **no structured product data** (its hotspots are only external links — newsletter, contests, travel), but the downloadable PDF has clean page images. This scraper renders each PDF page to an image and uses **Claude vision** (structured JSON output) to extract products (name, price, crossed-out `originalPrice`, `amount`, `unitPrice`, and a `category` chosen from the unified set in `categories.py` — so leaflet products get a real `normalizedCategory` instead of falling back to "Sonstiges"). The prompt restricts extraction to **grocery/drugstore assortment**: non-food leaflet items (clothing, toys, tools, electronics, mobile tariffs, travel) are skipped. The model defaults to the cheapest capable option, `claude-haiku-4-5` (OCR from clean leaflet images doesn't need more), and is overridable via the `HOFER_FLUGBLATT_MODEL` env var (e.g. `claude-sonnet-4-6` if dense small-print pages come out unreliable). Since extraction is cached per leaflet, cost is a few cents per week, not per run.

- **Discovery:** `katalog.hofer.at` redirects to the current flipbook (e.g. `flipbook_kw28_26_2`); the flipbook HTML embeds the Publitas PDF URL. Offer validity is parsed from the leaflet's first page ("MO. 6.7. BIS DO. 9.7.").
- **Caching:** results are cached per flipbook slug in `flugblatt_cache/{slug}.json` (gitignored), so the LLM only runs when a **new** leaflet is published (~weekly), not on every daily cron.
- **Credentials:** requires `ANTHROPIC_API_KEY`. Without it (and without a cache hit), extraction is skipped and an empty list is written — the daily run still succeeds.
- **IDs:** flugblatt products have no SKU, so a stable id is generated as `hofer_fb_<md5(brand|name|amount)>` — it can't collide with the online API's `hofer_<sku>` ids. Products carry `supermarket: "hofer"` (shown as Hofer in the app) but sync under their own `hofer_flugblatt` metadata bucket, so the two Hofer sources never delete each other's products.

**Flow:** discover current flipbook + PDF URL → (cache hit? return cached) → download PDF → render pages to PNG → Claude vision per page → parse JSON → build/dedupe products → cache → write `hofer_flugblatt.json`

## MPreis (`scrapers/mpreis.py`)

Uses **Playwright (sync)** to render three MPreis pages: `lebensmittel`, `getraenke`, and the `aktionen` page (`/aktionen/aktuell/alle-produkte-in-aktion`). For each page it dismisses the cookie banner and clicks "Mehr laden" until all tiles (`a.c3-product`) are loaded. Promotion detection happens via DOM (strike-through price, discount badge, screen-reader "statt"-price, multi-buy promo text); every product on the `aktionen` page is additionally forced to `inPromotion: true`. Products without a price are dropped, and products appearing on multiple pages are deduplicated by SKU.

**Flow:** launch headless Chromium → scrape three pages (click "load more" to load all) → deduplicate by SKU → write `mpreis.json`

## Error Handling & Debugging

- Playwright scrapers save **screenshots** to `screenshots/` on failure for CI debugging.
- Spar retries pages up to 5 times if the search returns an error ("Leider funktioniert unsere Suche").
- All scrapers catch per-category errors so a single failure doesn't abort the entire run.
