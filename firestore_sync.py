"""Diff-based Firestore sync.

Instead of delete-all / rewrite-all, this module:
1. Reads a single metadata document that stores MD5 hashes for every product.
2. Compares hashes locally to find new, changed, and removed products.
3. Only writes the delta in batched commits (max 500 ops per batch).

This dramatically reduces Firestore read/write/delete quota usage.
"""

import hashlib
import json
import time

MAX_RETRIES = 5
BATCH_COOLDOWN = 1.5
FIRESTORE_BATCH_LIMIT = 500  # Firestore maximum ops per batch
META_COLLECTION = "_sync_metadata"

# Firestore request counters – reset via reset_request_counters()
_request_counts: dict[str, int] = {"reads": 0, "writes": 0, "deletes": 0}


def reset_request_counters():
    """Reset all Firestore request counters to zero."""
    _request_counts["reads"] = 0
    _request_counts["writes"] = 0
    _request_counts["deletes"] = 0


def get_request_counts() -> dict[str, int]:
    """Return a copy of the current Firestore request counters."""
    return dict(_request_counts)


def _product_hash(product: dict) -> str:
    """Deterministic MD5 hash of a product dict for change detection."""
    serialized = json.dumps(product, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(serialized.encode()).hexdigest()


def _commit_with_retry(batch, label=""):
    """Commit a Firestore batch with exponential back-off."""
    for attempt in range(MAX_RETRIES):
        try:
            batch.commit()
            time.sleep(BATCH_COOLDOWN)
            return
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (2 ** attempt)
                print(f"  Batch commit failed ({label}), retrying in {wait}s… ({e})")
                time.sleep(wait)
            else:
                raise


def sync_products(db, products: list[dict], collection: str, meta_key: str | None = None):
    """Sync a list of products into *collection* using diff-based updates.

    Args:
        db: Firestore client.
        products: List of product dicts (each must have an ``"id"`` key).
        collection: Firestore collection name, e.g. ``"products"``.
        meta_key: Key for the metadata document in the ``_sync_metadata``
            collection.  Defaults to *collection* when not provided.  Use a
            supermarket-specific key (e.g. ``"billa"``) when multiple
            supermarkets share the same collection.

    Returns:
        Total number of Firestore write/delete operations performed.
    """
    if not db:
        return 0

    if meta_key is None:
        meta_key = collection

    if not products:
        print(f"  No products to sync for {meta_key}")
        return 0

    col_ref = db.collection(collection)

    # ── 1. Read existing hashes from the single metadata document ────────
    meta_ref = db.collection(META_COLLECTION).document(meta_key)
    meta_doc = meta_ref.get()
    _request_counts["reads"] += 1
    existing_hashes: dict[str, str] = (
        meta_doc.to_dict().get("hashes", {}) if meta_doc.exists else {}
    )
    print(f"  Existing products in Firestore: {len(existing_hashes)}")

    # ── 2. Compute hashes for the freshly scraped products ───────────────
    new_hashes: dict[str, str] = {}
    products_by_id: dict[str, dict] = {}
    for product in products:
        pid = product.get("id")
        if not pid:
            continue
        new_hashes[pid] = _product_hash(product)
        products_by_id[pid] = product

    # ── 3. Diff ──────────────────────────────────────────────────────────
    ids_to_write = [
        pid for pid, h in new_hashes.items() if existing_hashes.get(pid) != h
    ]
    ids_to_delete = list(set(existing_hashes.keys()) - set(new_hashes.keys()))

    unchanged = len(new_hashes) - len(ids_to_write)
    print(f"  Unchanged : {unchanged}")
    print(f"  To write  : {len(ids_to_write)}  (new + changed)")
    print(f"  To delete : {len(ids_to_delete)}  (removed)")

    if not ids_to_write and not ids_to_delete:
        print("  Nothing changed – skipping Firestore writes.")
        # Still update metadata in case the doc doesn't exist yet
        meta_ref.set({"hashes": new_hashes})
        _request_counts["writes"] += 1
        return 1  # 1 metadata write

    # ── 4. Batch-write new / changed products ────────────────────────────
    for i in range(0, len(ids_to_write), FIRESTORE_BATCH_LIMIT):
        batch = db.batch()
        chunk = ids_to_write[i : i + FIRESTORE_BATCH_LIMIT]
        for pid in chunk:
            batch.set(col_ref.document(pid), products_by_id[pid])
        _commit_with_retry(batch, f"write {collection} batch {i // FIRESTORE_BATCH_LIMIT + 1}")
        _request_counts["writes"] += len(chunk)
        print(f"  Written batch {i // FIRESTORE_BATCH_LIMIT + 1}  ({len(chunk)} docs)")

    # ── 5. Batch-delete removed products ─────────────────────────────────
    for i in range(0, len(ids_to_delete), FIRESTORE_BATCH_LIMIT):
        batch = db.batch()
        chunk = ids_to_delete[i : i + FIRESTORE_BATCH_LIMIT]
        for pid in chunk:
            batch.delete(col_ref.document(pid))
        _commit_with_retry(batch, f"delete {collection} batch {i // FIRESTORE_BATCH_LIMIT + 1}")
        _request_counts["deletes"] += len(chunk)
        print(f"  Deleted batch {i // FIRESTORE_BATCH_LIMIT + 1}  ({len(chunk)} docs)")

    # ── 6. Persist final hashes (ensures metadata is fully up to date) ───
    meta_ref.set({"hashes": new_hashes})
    _request_counts["writes"] += 1

    total_ops = len(ids_to_write) + len(ids_to_delete) + 1
    print(f"  Firestore operations: {total_ops}")
    return total_ops
