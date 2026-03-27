"""Shared fixtures for both unit and integration tests."""

import os
import pytest


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
    "supermarket",
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
