# Firestore Storage

The upload pipeline is split into two modules:

- **`firebase_store.py`** – initializes Firebase and dispatches per-supermarket syncs
- **`firestore_sync.py`** – performs the diff-based sync

## Data Layout

Each supermarket has its own product collection. A separate `_sync_metadata` collection holds one document per supermarket that maps every `product_id` to its MD5 hash — used to detect changes between runs.

```
_sync_metadata/
  billa_products        ← { hashes: { "billa_123": "abc…", … } }
  spar_products         ← { hashes: { "spar_456": "def…", … } }
  hofer_products        ← { hashes: { … } }
  penny_products        ← { hashes: { … } }

billa_products/
  billa_123             ← { id, name, price, … }
  …

spar_products/          ← same structure
hofer_products/         ← same structure
penny_products/         ← same structure
```

## Diff-Based Sync

Instead of deleting all documents and re-writing them on every run, `firestore_sync.py` uses a **hash-based diff** to minimise Firestore operations.

### Step 1 – Read metadata (1 read per supermarket)

The metadata document for the supermarket is fetched. It contains `{ product_id → MD5_hash }` for every product currently in Firestore. This costs exactly **1 read** regardless of product count.

### Step 2 – Compute new hashes (local)

Each scraped product is serialized to deterministic JSON (keys sorted) and hashed with MD5, producing a new in-memory `{ product_id → MD5_hash }` map.

### Step 3 – Diff (local)

Old and new hash maps are compared:

| Condition | Action |
|-----------|--------|
| Hash missing or different | **write** (`set`) to Firestore |
| ID no longer present | **delete** from Firestore |
| Hash identical | **skip** — no Firestore operation |

If nothing has changed, the run prints "Nothing changed – skipping Firestore writes." and exits after a single metadata refresh.

### Step 4 – Batched writes with retry

Writes and deletes are committed in **batches of up to 500 ops** (the Firestore per-batch limit):

- Failed commits are retried up to **5 times** with exponential back-off: 5 s, 10 s, 20 s, 40 s, 80 s.
- A **1.5 s cooldown** is applied between each successful batch to reduce rate-limit risk.
- **After each successful batch**, the metadata document is updated immediately (see Resumability).

Writes (new/changed) are processed before deletes (removed).

### Step 5 – Finalize metadata

After all batches complete, the metadata document is written one final time with the fully up-to-date hash map as a consistency safety net.

## Resumability

The metadata document is updated **after every individual batch**, not only at the end. If a run is interrupted mid-way (e.g. by a `429 Quota exceeded` timeout):

- The metadata already reflects all batches that succeeded.
- The next run's diff sees those products as unchanged and skips them.
- The run resumes from the first uncommitted batch rather than starting over.

## Quota Impact

A typical daily run where ~10% of prices change costs roughly:
- **4 reads** (1 metadata doc per supermarket)
- **N writes** (only new/changed products)
- **1 metadata write per committed batch**

If nothing changes between runs, **zero product documents are written**.
