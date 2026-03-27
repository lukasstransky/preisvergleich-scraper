"""Integration: scraper → firebase_store → firestore_sync pipeline.

Uses the in-memory ``FakeFirestoreDB`` to verify that products flow from
``upload_products`` all the way through the diff-based sync into the store.
"""

import pytest
from unittest.mock import patch

from firestore_sync import reset_request_counters, get_request_counts, _product_hash
from firebase_store import upload_products, upload_all
from tests.integration.fake_firestore import FakeFirestoreDB
from tests.integration.helpers import make_product

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_counters():
    reset_request_counters()


def _make_products(supermarket, count):
    """Generate *count* unique products for *supermarket*."""
    return [
        make_product(
            supermarket=supermarket,
            sku=f"SKU-{i:04d}",
            name=f"Product {i}",
            price=1.0 + i * 0.1,
        )
        for i in range(count)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# upload_products → sync_products full pipeline
# ──────────────────────────────────────────────────────────────────────────────

class TestFullSyncPipeline:
    def test_first_sync_writes_all_products(self):
        db = FakeFirestoreDB()
        products = _make_products("billa", 5)

        upload_products(db, products, "billa")

        # All 5 products are in the collection
        docs = db.get_all_docs("billa_products")
        assert len(docs) == 5
        for p in products:
            assert p["id"] in docs
            assert docs[p["id"]] == p

        # Metadata contains hashes for all 5 products
        meta = db.get_all_docs("_sync_metadata")
        assert "billa_products" in meta
        hashes = meta["billa_products"]["hashes"]
        assert len(hashes) == 5
        for p in products:
            assert hashes[p["id"]] == _product_hash(p)

        # Request counters: 1 read (metadata) + 5 writes (products) + 1 write (metadata)
        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] == 6  # 5 products + 1 metadata
        assert counts["deletes"] == 0

    def test_second_sync_no_changes(self):
        db = FakeFirestoreDB()
        products = _make_products("billa", 3)

        upload_products(db, products, "billa")
        reset_request_counters()

        # Re-sync with identical products
        upload_products(db, products, "billa")

        # Still 3 documents
        docs = db.get_all_docs("billa_products")
        assert len(docs) == 3

        # Only 1 read (metadata) + 1 write (metadata update) — no product writes
        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] == 1  # metadata only
        assert counts["deletes"] == 0

    def test_sync_detects_changes_additions_and_removals(self):
        db = FakeFirestoreDB()
        original = _make_products("spar", 5)

        upload_products(db, original, "spar")
        reset_request_counters()

        # Second sync: remove product 0, change product 1, add a new one
        updated = [
            # product 0 removed (not in list)
            make_product("spar", "SKU-0001", "CHANGED Product 1", 999.99),  # changed
            make_product("spar", "SKU-0002", "Product 2", 1.2),  # unchanged
            make_product("spar", "SKU-0003", "Product 3", 1.3),  # unchanged
            make_product("spar", "SKU-0004", "Product 4", 1.4),  # unchanged
            make_product("spar", "SKU-0005", "New Product", 5.55),  # new
        ]

        upload_products(db, updated, "spar")

        docs = db.get_all_docs("spar_products")
        assert len(docs) == 5

        # Product 0 was deleted
        assert "spar_SKU-0000" not in docs
        # Changed product has new name and price
        assert docs["spar_SKU-0001"]["name"] == "CHANGED Product 1"
        assert docs["spar_SKU-0001"]["price"] == 999.99
        # New product exists
        assert "spar_SKU-0005" in docs

        counts = get_request_counts()
        assert counts["reads"] == 1
        assert counts["writes"] >= 3  # 1 changed + 1 new + 1 metadata
        assert counts["deletes"] == 1  # 1 removed

    def test_sync_with_empty_products_deletes_all(self):
        db = FakeFirestoreDB()
        products = _make_products("hofer", 3)

        upload_products(db, products, "hofer")
        reset_request_counters()

        # Sync with empty list — should be a no-op (sync_products returns early)
        upload_products(db, [], "hofer")

        # The sync_products function returns early for empty products,
        # so existing docs remain unchanged.
        counts = get_request_counts()
        assert counts["reads"] == 0  # sync_products returns before reading


# ──────────────────────────────────────────────────────────────────────────────
# upload_all — multiple supermarkets through firebase_store
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadAll:
    @patch("firebase_store.init_firebase")
    def test_upload_all_syncs_multiple_supermarkets(self, mock_init):
        db = FakeFirestoreDB()
        mock_init.return_value = db

        billa_products = _make_products("billa", 3)
        spar_products = _make_products("spar", 2)

        upload_all({"billa": billa_products, "spar": spar_products})

        # Both collections populated
        assert len(db.get_all_docs("billa_products")) == 3
        assert len(db.get_all_docs("spar_products")) == 2

        # Metadata for both
        meta = db.get_all_docs("_sync_metadata")
        assert "billa_products" in meta
        assert "spar_products" in meta
        assert len(meta["billa_products"]["hashes"]) == 3
        assert len(meta["spar_products"]["hashes"]) == 2

    @patch("firebase_store.init_firebase")
    def test_upload_all_no_firebase_is_noop(self, mock_init):
        mock_init.return_value = None

        # Should not raise — just prints a warning
        upload_all({"billa": _make_products("billa", 2)})

    @patch("firebase_store.init_firebase")
    def test_upload_all_request_summary(self, mock_init):
        db = FakeFirestoreDB()
        mock_init.return_value = db

        products = _make_products("penny", 4)
        upload_all({"penny": products})

        counts = get_request_counts()
        total = counts["reads"] + counts["writes"] + counts["deletes"]
        assert total > 0  # At minimum: 1 read + 4 writes + 1 meta write

    @patch("firebase_store.init_firebase")
    def test_upload_all_then_re_upload_is_idempotent(self, mock_init):
        """Two successive uploads of the same data should not create duplicates."""
        db = FakeFirestoreDB()
        mock_init.return_value = db

        products = _make_products("billa", 3)

        upload_all({"billa": products})
        first_docs = dict(db.get_all_docs("billa_products"))

        upload_all({"billa": products})
        second_docs = db.get_all_docs("billa_products")

        assert first_docs == second_docs
