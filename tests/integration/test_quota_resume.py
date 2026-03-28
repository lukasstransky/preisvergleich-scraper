"""Integration: resume upload after quota limit was reached mid-sync.

Real-world scenario
-------------------
Day 1 – The scraper ran and called ``upload_all``.  Firestore quota was
exhausted while batch-writing one collection, so ``sync_products`` raised an
exception *before* it could persist the metadata document (step 6 in
``firestore_sync.sync_products``).  Some products already landed in the
collection; the metadata doc is missing or stale.

Day 2 – The user re-runs with ``--upload-only``.  The hashing check must:
  1. Re-upload all products for the interrupted collection (metadata is
     absent so the diff sees everything as "new" – safe & idempotent).
  2. Persist the metadata so a subsequent run is a no-op.
  3. Skip products for collections whose previous sync *did* complete
     (their metadata is correct and the data has not changed).

All tests use ``FakeFirestoreDB`` – no real Firestore calls.
"""

import pytest

from firestore_sync import (
    sync_products,
    reset_request_counters,
    get_request_counts,
    _product_hash,
    META_COLLECTION,
)
from firebase_store import upload_products, upload_all
from tests.integration.fake_firestore import FakeFirestoreDB
from tests.integration.helpers import make_product

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _products(supermarket: str, count: int, *, price_base: float = 1.0):
    return [
        make_product(supermarket, f"SKU-{i:04d}", f"Product {i}", price_base + i * 0.1)
        for i in range(count)
    ]


def _write_products_without_metadata(db: FakeFirestoreDB, products: list, collection: str):
    """Simulate a partial upload: products land in the collection but the
    metadata document is never written (mirrors a quota-hit scenario where the
    exception is raised during step 4 / before step 6 of sync_products)."""
    col = db.collection(collection)
    for p in products:
        col.document(p["id"]).set(p)
    # Deliberately do NOT touch META_COLLECTION


# ──────────────────────────────────────────────────────────────────────────────
# Core resume tests
# ──────────────────────────────────────────────────────────────────────────────

class TestResumeAfterQuotaHit:
    """sync_products correctly recovers when metadata is absent/stale."""

    def setup_method(self):
        reset_request_counters()

    # ------------------------------------------------------------------
    # 1. No metadata at all → all products written, metadata saved
    # ------------------------------------------------------------------
    def test_run2_uploads_everything_when_metadata_missing(self):
        """Day-2 run: products already in collection, metadata doc absent.

        Expected: all products are re-written (idempotent) and metadata is
        saved so that the Day-3 run is a no-op.
        """
        db = FakeFirestoreDB()
        products = _products("billa", 5)

        # Simulate Day-1 partial upload: products written, metadata missing.
        _write_products_without_metadata(db, products, "billa_products")

        reset_request_counters()

        # Day-2 run
        upload_products(db, products, "billa")

        # All 5 products still present
        docs = db.get_all_docs("billa_products")
        assert len(docs) == 5

        # Metadata was saved this time
        meta = db.get_all_docs(META_COLLECTION)
        assert "billa_products" in meta
        hashes = meta["billa_products"]["hashes"]
        assert len(hashes) == 5
        for p in products:
            assert hashes[p["id"]] == _product_hash(p)

        # At least: 1 read + 5 writes + 1 metadata write
        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] >= 6
        assert counts["deletes"] == 0

    # ------------------------------------------------------------------
    # 2. Day-3 run after successful Day-2 → zero product writes
    # ------------------------------------------------------------------
    def test_run3_is_noop_after_successful_run2(self):
        """After a complete sync the next run with identical data costs only
        1 read + 1 metadata write and performs zero product writes."""
        db = FakeFirestoreDB()
        products = _products("spar", 4)

        # Day-1 partial upload (no metadata)
        _write_products_without_metadata(db, products, "spar_products")

        # Day-2 full sync (saves metadata)
        upload_products(db, products, "spar")

        reset_request_counters()

        # Day-3 same products → should be a no-op
        upload_products(db, products, "spar")

        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] == 1   # metadata-only write
        assert counts["deletes"] == 0

    # ------------------------------------------------------------------
    # 3. Stale metadata (only N of M products recorded)
    # ------------------------------------------------------------------
    def test_stale_metadata_triggers_reupload_of_missing_products(self):
        """Quota was hit after the first batch of 3 products was written and
        metadata was saved for only those 3.  The remaining 2 were never
        uploaded.  The next run must upload the missing 2.
        """
        db = FakeFirestoreDB()
        all_products = _products("hofer", 5)
        uploaded_batch = all_products[:3]
        remaining = all_products[3:]

        # Day-1: first batch completed + metadata saved for those 3
        upload_products(db, uploaded_batch, "hofer")

        reset_request_counters()

        # Day-2: all 5 products (same run, just the full list)
        upload_products(db, all_products, "hofer")

        docs = db.get_all_docs("hofer_products")
        assert len(docs) == 5, "All 5 products must be in the collection"

        # The 2 previously-missing products must now exist
        for p in remaining:
            assert p["id"] in docs, f"{p['id']} was not uploaded on Day-2"

        # Metadata updated with all 5 hashes
        meta = db.get_all_docs(META_COLLECTION)
        hashes = meta["hofer_products"]["hashes"]
        assert len(hashes) == 5

        # Only the 2 new products + metadata were written (3 unchanged)
        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] == 3   # 2 new products + 1 metadata
        assert counts["deletes"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Mixed-collection scenario (the actual user workflow)
# ──────────────────────────────────────────────────────────────────────────────

class TestMixedCompleteAndIncompleteCollections:
    """upload_all with one fully-synced and one interrupted collection."""

    def setup_method(self):
        reset_request_counters()

    def test_completed_collection_skipped_incomplete_reuploaded(self):
        """Day-2 simulation:

        * ``penny`` completed on Day-1 → metadata saved → Day-2 diff finds
          nothing changed → 0 product writes (only 1 metadata write).
        * ``billa`` was interrupted on Day-1: batch writes landed in the
          collection but quota hit before step 6, so the metadata doc was
          never persisted.  Day-2 reads empty metadata → all 4 products look
          "new" to the diff → all 4 re-written idempotently → metadata saved.
        """
        from unittest.mock import patch

        db = FakeFirestoreDB()

        penny_products = _products("penny", 3)
        billa_products = _products("billa", 4)

        # Day-1 state for penny: full sync complete (metadata saved)
        upload_products(db, penny_products, "penny")

        # Day-1 state for billa: products written but metadata missing
        _write_products_without_metadata(db, billa_products, "billa_products")

        reset_request_counters()

        # Day-2: upload_all for both supermarkets
        with patch("firebase_store.init_firebase", return_value=db):
            upload_all({"penny": penny_products, "billa": billa_products})

        counts = get_request_counts()

        # penny: 1 read + 1 metadata write only (no product writes)
        # billa: 1 read + 4 product writes + 1 metadata write
        assert counts["reads"] == 2            # 1 per collection
        assert counts["writes"] == 6           # 0 penny products + 4 billa products + 2 metadata
        assert counts["deletes"] == 0

        # All products present in both collections
        assert len(db.get_all_docs("penny_products")) == 3
        assert len(db.get_all_docs("billa_products")) == 4

        # Both metadata docs exist and are correct
        meta = db.get_all_docs(META_COLLECTION)
        assert len(meta["penny_products"]["hashes"]) == 3
        assert len(meta["billa_products"]["hashes"]) == 4

    def test_day3_after_successful_day2_is_full_noop(self):
        """After Day-2 completes cleanly, Day-3 with unchanged data costs only
        1 read + 1 metadata write per collection."""
        from unittest.mock import patch

        db = FakeFirestoreDB()
        penny_products = _products("penny", 3)
        billa_products = _products("billa", 4)

        # Bring DB to the clean post-Day-2 state
        upload_products(db, penny_products, "penny")
        _write_products_without_metadata(db, billa_products, "billa_products")
        upload_products(db, billa_products, "billa")   # Day-2 billa

        reset_request_counters()

        # Day-3: same data, everything already in sync
        with patch("firebase_store.init_firebase", return_value=db):
            upload_all({"penny": penny_products, "billa": billa_products})

        counts = get_request_counts()
        # 2 reads + 2 metadata writes, zero product writes or deletes
        assert counts["reads"] == 2
        assert counts["writes"] == 2
        assert counts["deletes"] == 0
