"""Tests for firestore_sync.py – diff-based Firestore sync logic."""

import hashlib
import json
from unittest.mock import MagicMock, call, patch

import pytest

from firestore_sync import (
    _product_hash,
    _commit_with_retry,
    sync_products,
    FIRESTORE_BATCH_LIMIT,
    META_COLLECTION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product(pid, name="Test", price=1.0):
    """Create a minimal product dict for testing."""
    return {"id": pid, "name": name, "price": price, "supermarket": "test"}


def _expected_hash(product):
    """Compute the expected MD5 hash for a product dict."""
    serialized = json.dumps(product, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(serialized.encode()).hexdigest()


def _make_firestore_db(existing_hashes=None):
    """Build a mock Firestore client with a metadata document.

    Returns (db, meta_ref, col_ref, batches) where batches is a list that
    collects every batch object created via db.batch().
    """
    db = MagicMock()

    # Metadata document
    meta_doc = MagicMock()
    if existing_hashes is not None:
        meta_doc.exists = True
        meta_doc.to_dict.return_value = {"hashes": existing_hashes}
    else:
        meta_doc.exists = False

    meta_ref = MagicMock()
    meta_ref.get.return_value = meta_doc

    # Collection refs
    col_ref = MagicMock()

    def _collection(name):
        if name == META_COLLECTION:
            meta_col = MagicMock()
            meta_col.document.return_value = meta_ref
            return meta_col
        return col_ref

    db.collection.side_effect = _collection

    # Track batches
    batches = []

    def _make_batch():
        b = MagicMock()
        batches.append(b)
        return b

    db.batch.side_effect = _make_batch

    return db, meta_ref, col_ref, batches


# ---------------------------------------------------------------------------
# _product_hash
# ---------------------------------------------------------------------------

class TestProductHash:
    def test_deterministic(self):
        p = _make_product("p1", "Apple", 1.99)
        assert _product_hash(p) == _product_hash(p)

    def test_key_order_irrelevant(self):
        p1 = {"id": "p1", "name": "A", "price": 1.0}
        p2 = {"price": 1.0, "id": "p1", "name": "A"}
        assert _product_hash(p1) == _product_hash(p2)

    def test_different_data_different_hash(self):
        p1 = _make_product("p1", "Apple", 1.0)
        p2 = _make_product("p1", "Apple", 2.0)
        assert _product_hash(p1) != _product_hash(p2)

    def test_unicode_handling(self):
        p = _make_product("p1", "Käse Würstel", 3.5)
        h = _product_hash(p)
        assert isinstance(h, str)
        assert len(h) == 32  # MD5 hex digest length

    def test_matches_manual_md5(self):
        p = _make_product("p1")
        assert _product_hash(p) == _expected_hash(p)


# ---------------------------------------------------------------------------
# _commit_with_retry
# ---------------------------------------------------------------------------

class TestCommitWithRetry:
    @patch("firestore_sync.time.sleep")
    def test_success_first_attempt(self, mock_sleep):
        batch = MagicMock()
        _commit_with_retry(batch, "test")
        batch.commit.assert_called_once()

    @patch("firestore_sync.time.sleep")
    def test_retries_on_failure(self, mock_sleep):
        batch = MagicMock()
        batch.commit.side_effect = [Exception("transient"), None]
        _commit_with_retry(batch, "test")
        assert batch.commit.call_count == 2

    @patch("firestore_sync.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        batch = MagicMock()
        batch.commit.side_effect = Exception("persistent")
        with pytest.raises(Exception, match="persistent"):
            _commit_with_retry(batch, "test")
        assert batch.commit.call_count == 5  # MAX_RETRIES

    @patch("firestore_sync.time.sleep")
    def test_exponential_backoff_wait_times(self, mock_sleep):
        batch = MagicMock()
        # Fail 3 times, then succeed
        batch.commit.side_effect = [
            Exception("err"),
            Exception("err"),
            Exception("err"),
            None,
        ]
        _commit_with_retry(batch, "test")
        # Check backoff waits: 5*1=5, 5*2=10, 5*4=20 (before success)
        sleep_values = [c.args[0] for c in mock_sleep.call_args_list]
        # After failure: wait 5, 10, 20 then after success: BATCH_COOLDOWN
        assert 5 in sleep_values
        assert 10 in sleep_values
        assert 20 in sleep_values


# ---------------------------------------------------------------------------
# sync_products – core logic
# ---------------------------------------------------------------------------

class TestSyncProductsNoDb:
    def test_returns_zero_when_db_is_none(self):
        result = sync_products(None, [_make_product("p1")], "test_products")
        assert result == 0

    def test_returns_zero_when_products_empty(self):
        db = MagicMock()
        result = sync_products(db, [], "test_products")
        assert result == 0


class TestSyncProductsFirstRun:
    """First run – no existing metadata → everything is new."""

    @patch("firestore_sync.time.sleep")
    def test_all_products_written(self, mock_sleep):
        products = [_make_product("p1"), _make_product("p2"), _make_product("p3")]
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=None)

        ops = sync_products(db, products, "test_products")

        # All 3 products should be written + 1 metadata write
        assert ops == 4
        # One batch created for writes
        assert len(batches) == 1
        assert batches[0].set.call_count == 3
        batches[0].commit.assert_called_once()
        # Metadata updated
        meta_ref.set.assert_called_once()
        meta_hashes = meta_ref.set.call_args[0][0]["hashes"]
        assert len(meta_hashes) == 3

    @patch("firestore_sync.time.sleep")
    def test_no_deletes_on_first_run(self, mock_sleep):
        products = [_make_product("p1")]
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=None)

        sync_products(db, products, "test_products")

        # Only set calls, no delete calls
        for batch in batches:
            batch.delete.assert_not_called()


class TestSyncProductsNothingChanged:
    """All products identical → no writes except metadata."""

    @patch("firestore_sync.time.sleep")
    def test_skips_writes_when_nothing_changed(self, mock_sleep):
        p1 = _make_product("p1", "Apple", 1.0)
        p2 = _make_product("p2", "Banana", 2.0)
        existing = {
            "p1": _expected_hash(p1),
            "p2": _expected_hash(p2),
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        ops = sync_products(db, [p1, p2], "test_products")

        # Only the metadata write
        assert ops == 1
        # No batches created (no writes/deletes needed)
        assert len(batches) == 0
        # Metadata still updated
        meta_ref.set.assert_called_once()


class TestSyncProductsChangedProducts:
    """Some products changed → only those are written."""

    @patch("firestore_sync.time.sleep")
    def test_writes_only_changed_products(self, mock_sleep):
        p1 = _make_product("p1", "Apple", 1.0)
        p2_old = _make_product("p2", "Banana", 2.0)
        p2_new = _make_product("p2", "Banana", 2.50)  # price changed

        existing = {
            "p1": _expected_hash(p1),
            "p2": _expected_hash(p2_old),
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        ops = sync_products(db, [p1, p2_new], "test_products")

        # 1 changed product + 1 metadata
        assert ops == 2
        assert len(batches) == 1
        assert batches[0].set.call_count == 1  # only p2
        batches[0].delete.assert_not_called()

    @patch("firestore_sync.time.sleep")
    def test_writes_new_product(self, mock_sleep):
        p1 = _make_product("p1", "Apple", 1.0)
        p2 = _make_product("p2", "Banana", 2.0)  # new

        existing = {"p1": _expected_hash(p1)}
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        ops = sync_products(db, [p1, p2], "test_products")

        # 1 new product + 1 metadata
        assert ops == 2
        assert len(batches) == 1
        assert batches[0].set.call_count == 1


class TestSyncProductsDeletedProducts:
    """Products removed from scrape data → deleted from Firestore."""

    @patch("firestore_sync.time.sleep")
    def test_deletes_removed_products(self, mock_sleep):
        p1 = _make_product("p1", "Apple", 1.0)
        p2 = _make_product("p2", "Banana", 2.0)

        existing = {
            "p1": _expected_hash(p1),
            "p2": _expected_hash(p2),
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        # Only p1 in new data → p2 should be deleted
        ops = sync_products(db, [p1], "test_products")

        # 1 delete + 1 metadata
        assert ops == 2
        # One batch for deletes
        delete_batch = None
        for b in batches:
            if b.delete.call_count > 0:
                delete_batch = b
        assert delete_batch is not None
        assert delete_batch.delete.call_count == 1

    @patch("firestore_sync.time.sleep")
    def test_deletes_all_when_empty_products_not_triggered(self, mock_sleep):
        """sync_products returns 0 for empty products list (early return)."""
        existing = {"p1": "somehash", "p2": "anotherhash"}
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        ops = sync_products(db, [], "test_products")
        assert ops == 0


class TestSyncProductsMixedChanges:
    """Combination of new, changed, unchanged, and removed products."""

    @patch("firestore_sync.time.sleep")
    def test_mixed_operations(self, mock_sleep):
        p_unchanged = _make_product("p1", "Apple", 1.0)
        p_changed_old = _make_product("p2", "Banana", 2.0)
        p_changed_new = _make_product("p2", "Banana", 2.50)
        p_new = _make_product("p3", "Cherry", 3.0)
        p_removed = _make_product("p4", "Date", 4.0)

        existing = {
            "p1": _expected_hash(p_unchanged),
            "p2": _expected_hash(p_changed_old),
            "p4": _expected_hash(p_removed),
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        ops = sync_products(
            db,
            [p_unchanged, p_changed_new, p_new],
            "test_products",
        )

        # 2 writes (p2 changed, p3 new) + 1 delete (p4) + 1 metadata = 4
        assert ops == 4

        # Verify metadata contains exactly the 3 current products
        meta_hashes = meta_ref.set.call_args[0][0]["hashes"]
        assert set(meta_hashes.keys()) == {"p1", "p2", "p3"}


class TestSyncProductsBatching:
    """Verify batching at FIRESTORE_BATCH_LIMIT boundaries."""

    @patch("firestore_sync.time.sleep")
    @patch("firestore_sync.FIRESTORE_BATCH_LIMIT", 2)
    def test_splits_writes_into_batches(self, mock_sleep):
        products = [_make_product(f"p{i}") for i in range(5)]
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=None)

        ops = sync_products(db, products, "test_products")

        # 5 products in batches of 2 → 3 write batches
        assert len(batches) == 3
        assert batches[0].set.call_count == 2
        assert batches[1].set.call_count == 2
        assert batches[2].set.call_count == 1
        assert ops == 6  # 5 writes + 1 metadata

    @patch("firestore_sync.time.sleep")
    @patch("firestore_sync.FIRESTORE_BATCH_LIMIT", 2)
    def test_splits_deletes_into_batches(self, mock_sleep):
        p1 = _make_product("p1")
        existing = {
            "p1": _expected_hash(p1),
            "p2": "oldhash",
            "p3": "oldhash",
            "p4": "oldhash",
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        # Only p1 remains → 3 deletes
        ops = sync_products(db, [p1], "test_products")

        # Count delete batches (batches with delete calls)
        delete_calls = sum(b.delete.call_count for b in batches)
        assert delete_calls == 3
        # 3 deletes + 1 metadata = 4
        assert ops == 4


class TestSyncProductsSkipsNoId:
    """Products without an 'id' key are ignored."""

    @patch("firestore_sync.time.sleep")
    def test_skips_products_without_id(self, mock_sleep):
        products = [
            {"name": "No ID", "price": 1.0},
            _make_product("p1", "Has ID", 2.0),
        ]
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=None)

        ops = sync_products(db, products, "test_products")

        # Only p1 written + metadata
        assert ops == 2
        meta_hashes = meta_ref.set.call_args[0][0]["hashes"]
        assert "p1" in meta_hashes
        assert len(meta_hashes) == 1


class TestSyncProductsMetadata:
    """Verify metadata document is always updated correctly."""

    @patch("firestore_sync.time.sleep")
    def test_metadata_contains_all_current_hashes(self, mock_sleep):
        products = [
            _make_product("p1", "A", 1.0),
            _make_product("p2", "B", 2.0),
        ]
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=None)

        sync_products(db, products, "test_products")

        meta_hashes = meta_ref.set.call_args[0][0]["hashes"]
        assert meta_hashes == {
            "p1": _expected_hash(products[0]),
            "p2": _expected_hash(products[1]),
        }

    @patch("firestore_sync.time.sleep")
    def test_metadata_removes_deleted_product_hashes(self, mock_sleep):
        p1 = _make_product("p1")
        existing = {
            "p1": _expected_hash(p1),
            "p2": "will_be_deleted",
        }
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        sync_products(db, [p1], "test_products")

        meta_hashes = meta_ref.set.call_args[0][0]["hashes"]
        assert "p2" not in meta_hashes
        assert "p1" in meta_hashes


class TestSyncProductsOutput:
    """Verify console output reports correct counts."""

    @patch("firestore_sync.time.sleep")
    def test_prints_diff_summary(self, mock_sleep, capsys):
        p1 = _make_product("p1", "A", 1.0)
        p2 = _make_product("p2", "B", 2.0)
        existing = {"p1": _expected_hash(p1)}

        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)
        sync_products(db, [p1, p2], "test_products")

        output = capsys.readouterr().out
        assert "Unchanged : 1" in output
        assert "To write  : 1" in output
        assert "To delete : 0" in output

    @patch("firestore_sync.time.sleep")
    def test_prints_nothing_changed(self, mock_sleep, capsys):
        p1 = _make_product("p1")
        existing = {"p1": _expected_hash(p1)}
        db, meta_ref, col_ref, batches = _make_firestore_db(existing_hashes=existing)

        sync_products(db, [p1], "test_products")

        output = capsys.readouterr().out
        assert "Nothing changed" in output
