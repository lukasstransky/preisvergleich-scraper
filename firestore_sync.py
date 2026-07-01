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


def _write_price_history(db, collection: str, products: list[dict]) -> int:
    """Write price history entries to products/{id}/price_history/{date}.

    Only called for products whose price changed or are newly scraped.
    Returns the number of history entries written.
    """
    if not products:
        return 0

    today = datetime.date.today().isoformat()
    count = 0

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
        _commit_with_retry(batch, f"price_history batch {i // FIRESTORE_BATCH_LIMIT + 1}")
        count += len(chunk)
        print(f"  Price history batch {i // FIRESTORE_BATCH_LIMIT + 1}  ({len(chunk)} entries)")

    return count


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

    # ── 1. Read existing hashes from the metadata document ──────────────
    meta_ref = db.collection(META_COLLECTION).document(meta_key)
    meta_doc = meta_ref.get()
    _request_counts["reads"] += 1
    existing_hashes: dict[str, str] = (
        meta_doc.to_dict().get("hashes", {}) if meta_doc.exists else {}
    )
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

    # Write a price history entry for every product being written that has a
    # price field. Using the date as document ID makes this idempotent.
    products_for_history = [
        products_by_id[pid] for pid in ids_to_write
        if products_by_id[pid].get("price") is not None
    ]

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

    # ── 6. Persist final hashes ───────────────────────────────────────────
    # Do this BEFORE price history: the product writes/deletes above already
    # succeeded, so the hashes must be saved even if the (optional) price
    # history hits the daily write quota. Otherwise a price-history failure
    # would leave the metadata stale, making the next run treat every product
    # as changed and rewrite everything — a quota-blowing loop.
    meta_ref.set({"hashes": new_hashes})
    _request_counts["writes"] += 1

    # ── 7. Batch-write price history for all written products ────────────
    # Best-effort: a quota error here must not fail the whole sync, since the
    # product data and metadata are already consistent.
    history_count = 0
    try:
        history_count = _write_price_history(db, collection, products_for_history)
        _request_counts["writes"] += history_count
    except Exception as e:
        print(f"  Price history skipped (non-fatal): {e}")

    total_ops = len(ids_to_write) + len(ids_to_delete) + history_count + 1
    print(f"  Firestore operations: {total_ops}")
    return total_ops
