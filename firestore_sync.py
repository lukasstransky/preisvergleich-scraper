"""Diff-based Firestore sync.

Instead of delete-all / rewrite-all, this module:
1. Reads a single metadata document that stores MD5 hashes and last-known prices.
2. Compares hashes locally to find new, changed, and removed products.
3. Only writes the delta in batched commits (max 500 ops per batch).
4. For products being written whose price changed, appends an entry to the
   products/{id}/price_history/{YYYY-MM-DD} subcollection.

This dramatically reduces Firestore read/write/delete quota usage.
"""

import datetime
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


def _write_price_history(db, collection: str, products: list[dict]) -> set:
    """Write price history entries to products/{id}/price_history/{date}.

    Only called for products whose price actually changed (or that have no
    recorded price yet). Best-effort: on a commit failure it stops after the
    last successful batch instead of raising.

    Returns the set of product ids whose history entry was written, so the
    caller only records those prices as persisted.
    """
    written: set = set()
    if not products:
        return written

    today = datetime.date.today().isoformat()

    for i in range(0, len(products), FIRESTORE_BATCH_LIMIT):
        batch = db.batch()
        chunk = products[i : i + FIRESTORE_BATCH_LIMIT]
        for product in chunk:
            pid = product["id"]
            history_ref = (
                db.collection(collection)
                .document(pid)
                .collection("price_history")
                .document(today)
            )
            batch.set(history_ref, {"price": product["price"], "date": today})
        try:
            _commit_with_retry(batch, f"price_history batch {i // FIRESTORE_BATCH_LIMIT + 1}")
        except Exception as e:
            print(f"  Price history stopped at batch {i // FIRESTORE_BATCH_LIMIT + 1} (non-fatal): {e}")
            break
        written.update(product["id"] for product in chunk)
        print(f"  Price history batch {i // FIRESTORE_BATCH_LIMIT + 1}  ({len(chunk)} entries)")

    return written


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

    # ── 1. Read existing hashes and last-known prices from metadata ─────
    meta_ref = db.collection(META_COLLECTION).document(meta_key)
    meta_doc = meta_ref.get()
    _request_counts["reads"] += 1
    meta_data = meta_doc.to_dict() if meta_doc.exists else {}
    existing_hashes: dict[str, str] = meta_data.get("hashes", {})
    # Last price for which a history entry was recorded, per product id.
    existing_prices: dict[str, float] = meta_data.get("prices", {})
    print(f"  Existing products in Firestore: {len(existing_hashes)}")

    # ── 2. Compute hashes for freshly scraped products ───────────────────
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

    # Write a price history entry only for products whose price actually
    # changed, or that have no recorded price yet (e.g. a prior run's history
    # failed). This is independent of the hash diff — a product can be
    # unchanged hash-wise but still be missing its baseline history entry.
    # Date-as-document-id keeps each day idempotent.
    products_for_history = [
        products_by_id[pid] for pid in new_hashes
        if products_by_id[pid].get("price") is not None
        and existing_prices.get(pid) != products_by_id[pid]["price"]
    ]

    unchanged = len(new_hashes) - len(ids_to_write)
    print(f"  Unchanged : {unchanged}")
    print(f"  To write  : {len(ids_to_write)}  (new + changed)")
    print(f"  To delete : {len(ids_to_delete)}  (removed)")
    print(f"  Price history: {len(products_for_history)}  (price changed / new)")

    if not ids_to_write and not ids_to_delete and not products_for_history:
        print("  Nothing changed – skipping Firestore writes.")
        # Still update metadata in case the doc doesn't exist yet
        meta_ref.set({"hashes": new_hashes, "prices": existing_prices})
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

    # ── 6. Batch-write price history (best-effort) ───────────────────────
    # Returns the ids whose history was actually written this run.
    written_history_ids = _write_price_history(db, collection, products_for_history)
    _request_counts["writes"] += len(written_history_ids)

    # ── 7. Persist hashes + last-known prices ─────────────────────────────
    # Carry prior prices forward, update only the ones whose history we just
    # wrote (so a failed history entry is retried next run instead of being
    # silently skipped), and drop deleted products.
    new_prices = dict(existing_prices)
    for product in products_for_history:
        if product["id"] in written_history_ids:
            new_prices[product["id"]] = product["price"]
    for pid in ids_to_delete:
        new_prices.pop(pid, None)

    meta_ref.set({"hashes": new_hashes, "prices": new_prices})
    _request_counts["writes"] += 1

    total_ops = len(ids_to_write) + len(ids_to_delete) + len(written_history_ids) + 1
    print(f"  Firestore operations: {total_ops}")
    return total_ops
