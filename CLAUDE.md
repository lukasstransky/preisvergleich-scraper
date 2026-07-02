# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Python scrapers that collect product prices from Austrian supermarkets (Billa, Penny, Lidl, SPAR, Hofer, MPreis) and sync them into a single Google Cloud Firestore `products` collection. A separate Flutter app (not in this repo) consumes that data for price comparison, price-change notifications, and shopping lists.

## Commands

Always work inside the virtualenv:

```bash
python3 -m venv venv           # once
source venv/bin/activate       # every session
pip install -r requirements.txt
playwright install chromium    # bundled Chromium (not available on ARM — see below)
```

Run the pipeline:

```bash
python main.py                              # scrape all active scrapers + Firestore sync
python main.py --no-upload                  # scrape only, write JSON, no Firestore
python main.py --upload-only                # upload existing *.json without re-scraping
python main.py --scraper spar penny         # run a subset
python main.py --scraper spar --no-upload --spar-categories obst-gemuese   # SPAR quick test
```

Tests (`pytest.ini` sets `asyncio_mode = auto`):

```bash
pytest                                      # everything
pytest tests/test_spar.py                   # one file
pytest tests/test_spar.py::TestX::test_y    # one test
pytest -m integration                       # integration tests only (mocked Firestore, no network)
pytest -m "not integration"                 # unit tests only
```

## Architecture

**Orchestration.** `main.py` holds the `SCRAPERS` dict mapping name → `(json_file, scrape_fn)`. Each scraper is a plain function returning a `list[dict]` of products with a shared schema. `main.py` deletes stale JSON, runs each scraper, writes its JSON, then calls `firebase_store.upload_all`. **MPreis is intentionally commented out** of `SCRAPERS` (its scraper exists and is tested, but isn't run).

**Two scraper styles** (both produce the same product dict):
- REST API — `billa.py`, `penny.py`, `lidl.py` (fast, `requests`).
- Playwright — `spar.py` (async), `hofer.py` (sync), `mpreis.py` (async), rendering the DOM.

Per-scraper details, product schema, and ID strategies live in [docs/scrapers.md](docs/scrapers.md) and [docs/fields-by-scraper.md](docs/fields-by-scraper.md). Every product runs through two shared utilities: `scrapers/categories.py` `normalize_category()` (maps each store's taxonomy to ~15 unified German categories) and `scrapers/tokenizer.py` `tokenize_name()` (search tokens). Playwright launches go through `scrapers/browser.py` `launch_kwargs()`.

**Firestore sync is diff-based and quota-sensitive** — this is the core of the system. `firebase_store.upload_all` → `firestore_sync.sync_products` per supermarket. All stores share one flat `products` collection; each store has its own metadata doc in `_sync_metadata/{supermarket}` holding `{hashes, prices}`:
- Products are MD5-hashed; only new/changed products are written and removed ones deleted (compared against stored `hashes`).
- **Price history** (`products/{id}/price_history/{YYYY-MM-DD}`) is deliberately **sparse**: an entry is written only when a product's price differs from the stored `prices` value, or when no price is recorded yet (backfill). A stable price produces no new entries — the app forward-fills. Date-as-doc-id makes same-day reruns idempotent.
- Ordering matters: product writes/deletes happen first, price history is **best-effort** (a failure logs and continues), and stored prices are updated **only** for history entries that actually committed — so a failed price-history write is retried next run instead of being silently skipped. See [docs/firestore.md](docs/firestore.md).

Why this design: Firestore's free (Spark) tier caps at 20,000 writes/day. A single full scrape can exceed that on first run, so the diff + sparse history keep steady-state writes tiny. A production deployment needs the Blaze plan.

**Credentials.** `firebase_store.init_firebase()` resolves in order: `FIREBASE_KEY` env var (service-account JSON string) → `firebase-key.json` in root. If neither exists, scraping still runs but upload is skipped. `firebase-key.json` is gitignored.

## Running on a Raspberry Pi (daily cron)

`run.sh` is the cron entrypoint: it resolves its own directory, activates the venv, runs `python main.py`, and writes a timestamped log to `logs/` (keeping the last 14). It exports env vars needed on the Pi:

- `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium` — Playwright ships **no ARM Chromium**, so the Pi uses apt's system Chromium. `launch_kwargs()` reads this var (unset → bundled browser, e.g. on macOS).
- `SPAR_MAX_CONCURRENT=1` — SPAR's category concurrency (`MAX_CONCURRENT`, default 2). On the Pi, two concurrent Chromium contexts peg the CPU and make pagination clicks flaky, so it's set to 1.
- `PYTHONUNBUFFERED=1` — so log output isn't buffered when redirected to a file.

SPAR pagination is the fragile part on slow hardware: it clicks a "next page" button and polls (`_verify_page_num`, tile-presence polling, click retries) rather than assuming an instant render. When touching `spar.py`, preserve these polling/retry loops.

## Conventions

- Scrapers must not persist product images or long description text — only factual fields (name, price, brand, amount, category, `imageUrl` as a hotlink at most). This is a deliberate legal/copyright constraint for the downstream app.
- When changing the product dict or the sync contract, update the sync tests in `tests/test_firestore_sync.py` (metadata stores `hashes` + `prices`) and the integration tests under `tests/integration/` (which use `fake_firestore.py`, not real Firestore).
- CI: `.github/workflows/test.yml` runs `pytest tests/ -v` on every push/PR. The scraper workflow is manual-dispatch only (scheduled scraping in CI doesn't work reliably); the real schedule is the Pi cron job.
