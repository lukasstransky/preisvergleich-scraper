# Firestore Storage

The upload pipeline is split into two modules:

- **`firebase_store.py`** – initializes Firebase and dispatches per-supermarket syncs into a single `products` collection
- **`firestore_sync.py`** – performs the diff-based sync

## Data Layout

All supermarkets share a single flat `products` collection in Firestore. Price history lives in a per-product subcollection.

```
products/
  billa_123             ← { id, name, price, supermarket: "billa", … }
    price_history/
      2026-07-01        ← { price, date }   (sparse: only days the price changed)
  spar_456              ← { id, name, price, supermarket: "spar", … }
  …
```

The **sync metadata** (per-product hashes + last-known prices) is NOT in Firestore. It holds one entry per product; as a single Firestore document it would breach the per-document limits (40k index entries / 1 MiB). It lives on disk instead, one file per supermarket:

```
sync_state/               (gitignored; override dir via SYNC_STATE_DIR)
  billa.json              ← { "hashes": { "billa_123": "abc…", … },
                              "prices": { "billa_123": 1.39, … } }
  spar.json               ← { "hashes": { … }, "prices": { … } }
```

This is pure sync bookkeeping the app never reads, so a local file (per machine running the sync) is the natural home. Using a single `products` collection keeps app queries and search-service integration (e.g. Algolia) simple.

## Diff-Based Sync

Instead of deleting all documents and re-writing them on every run, `firestore_sync.py` uses a **hash-based diff** to minimise Firestore operations.

1. **Load local state** — read `sync_state/{supermarket}.json` (no Firestore read). Missing file → treat everything as new.
2. **Compute new hashes** — each scraped product is serialized to deterministic JSON (keys sorted) and MD5-hashed.
3. **Diff** — compare old vs new hash maps:

   | Condition | Action |
   |-----------|--------|
   | Hash missing or different | **write** (`set`) to Firestore |
   | ID no longer present | **delete** from Firestore |
   | Hash identical | **skip** — no Firestore op |

4. **Batched writes** — writes (new/changed) then deletes, in batches of up to 500 ops. Failed commits retry up to 5× with exponential back-off (5→10→20→40→80 s), with a 1.5 s cooldown between batches.
5. **Save local state** — after the product writes/deletes succeed, `sync_state/{supermarket}.json` is written with the new hashes + prices. This happens *before* price history so a price-history failure can't leave the state stale (which would make the next run rewrite everything).
6. **Price history (best-effort)** — a `price_history/{date}` entry is written only for products whose price actually changed, or that have no recorded price yet (backfill). A quota/commit failure here is logged and skipped, not fatal; only successfully-written prices are recorded in local state, so a failed entry is retried next run.

If nothing changed (no writes, deletes, or price-history entries), the run prints "Nothing changed – skipping Firestore writes." and only refreshes the local state file.

## Quota Impact

Because the metadata is local, a sync performs **zero Firestore reads**. A typical daily run where ~10% of prices change costs roughly N writes (changed products) + M writes (price-history entries for the price-changed subset). If nothing changed, **zero Firestore operations** occur. The first full run (or a fresh `sync_state/`) writes every product plus a baseline price-history entry each.
