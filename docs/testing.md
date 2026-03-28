# Testing

The project has two complementary test layers, both run with `pytest`:

```bash
pytest tests/ -v              # all tests
pytest tests/integration/ -v  # integration tests only
```

## Unit Tests (`tests/`)

Isolate individual functions (parsers, hash logic, Firestore diff algorithm, CLI helpers). All external I/O is mocked.

## Integration Tests (`tests/integration/`)

Exercise multi-component flows end-to-end with transport-level mocks — no real HTTP, browsers, or Firebase.

| File | What it covers |
|------|----------------|
| `test_schema_consistency.py` | All 4 scrapers produce products with consistent keys & types |
| `test_scraper_json_roundtrip.py` | Scraper function → JSON written to disk → read back & validated |
| `test_main_flow.py` | `main()` normal mode, `--no-upload`, and error propagation |
| `test_upload_only.py` | `--upload-only` with real files, missing files, and empty files |
| `test_firebase_pipeline.py` | Products flow through `firebase_store` → `firestore_sync` → flat `products` collection in in-memory Firestore fake |
| `test_quota_resume.py` | Resume upload after quota limit was reached mid-sync |

> `pytest-asyncio` is required for the async Spar scraper tests — included in `requirements.txt`.

## Data Quality (`analyze_json.py`)

Checks scraped JSON files for data issues:

```bash
python analyze_json.py spar.json                          # single file
python analyze_json.py spar.json billa.json hofer.json    # multiple files
python analyze_json.py                                    # auto-discover all *.json files
```

Checks performed:
- Missing or empty required fields (`id`, `name`, `price`, `category`, `supermarket`)
- Null, zero, negative, or non-numeric prices
- Duplicate IDs and exact duplicate entries
- `price > originalPrice` inconsistencies
- Promotion flag mismatches (`inPromotion` without `originalPrice` and vice versa)
- Missing optional fields (`sku`, `amount`, `imageUrl`, `brand`)
- Suspiciously high prices (> 500 EUR)
- Price statistics (min, max, avg, median)
