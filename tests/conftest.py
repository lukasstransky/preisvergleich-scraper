"""Shared fixtures for both unit and integration tests."""

import os
import pytest

import firestore_sync


@pytest.fixture(autouse=True)
def _isolate_sync_state(tmp_path, monkeypatch):
    """Point sync metadata at a fresh temp dir for every test.

    Metadata now lives on disk (``sync_state/``); isolating it per test keeps
    runs from sharing state or polluting the project root.
    """
    monkeypatch.setattr(firestore_sync, "SYNC_STATE_DIR", str(tmp_path / "sync_state"))


REQUIRED_PRODUCT_KEYS = {
    "id",
    "name",
    "price",
    "originalPrice",
    "promotionText",
    "unitPrice",
    "unitLabel",
    "category",
    "brand",
    "sku",
    "inPromotion",
    "imageUrl",
    "productUrl",
    "offerStart",
    "offerEnd",
    "supermarket",
    "nameTokens",
    "normalizedCategory",
    "nameLength",
}

# Spar and Hofer include an extra 'amount' key
OPTIONAL_PRODUCT_KEYS = {"amount"}


@pytest.fixture()
def product_schema_keys():
    """Return the canonical set of required product-dict keys."""
    return REQUIRED_PRODUCT_KEYS


@pytest.fixture()
def tmp_workdir(tmp_path, monkeypatch):
    """Change the working directory to a temp folder.

    Scrapers write JSON files relative to ``os.getcwd()``, so this fixture
    prevents test runs from polluting the project root.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path
