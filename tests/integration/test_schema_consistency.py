"""Integration: verify all 4 scrapers produce products with a consistent schema.

Each scraper is run with transport-level mocks (mocked HTTP / Playwright) but
the full internal parsing pipeline is exercised.  The test then checks that
every product from every scraper contains the expected keys with correct types.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import REQUIRED_PRODUCT_KEYS, OPTIONAL_PRODUCT_KEYS
from tests.integration.helpers import (
    SAMPLE_BILLA_PRODUCTS,
    SAMPLE_SPAR_TILES,
    SAMPLE_HOFER_API_ITEMS,
    make_billa_api_response,
    make_penny_offers_html,
    make_spar_mock_page,
    make_spar_mock_browser,
    make_hofer_api_response,
)

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────────────────
# Schema validation helper
# ──────────────────────────────────────────────────────────────────────────────

def _validate_product(product, supermarket):
    """Assert a product dict conforms to the canonical schema."""
    keys = set(product.keys())
    missing = REQUIRED_PRODUCT_KEYS - keys
    extra = keys - REQUIRED_PRODUCT_KEYS - OPTIONAL_PRODUCT_KEYS
    assert not missing, f"Missing keys {missing} in product {product.get('id')}"
    assert not extra, f"Unexpected keys {extra} in product {product.get('id')}"

    assert product["supermarket"] == supermarket
    assert isinstance(product["id"], str) and product["id"].startswith(f"{supermarket}_")
    assert isinstance(product["inPromotion"], bool)
    assert product["price"] is None or isinstance(product["price"], (int, float))
    assert product["imageUrl"] is None or isinstance(product["imageUrl"], str)
    assert product["name"] is None or isinstance(product["name"], str)


# ──────────────────────────────────────────────────────────────────────────────
# Billa
# ──────────────────────────────────────────────────────────────────────────────

class TestBillaSchema:
    @patch("scrapers.billa.CATEGORIES", ["obst-und-gemuese-13751"])
    @patch("scrapers.billa.requests.get")
    def test_billa_product_schema(self, mock_get, tmp_workdir):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = make_billa_api_response(SAMPLE_BILLA_PRODUCTS)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        from scrapers.billa import scrape_billa
        products = scrape_billa()

        assert len(products) == 3
        for p in products:
            _validate_product(p, "billa")


# ──────────────────────────────────────────────────────────────────────────────
# Penny
# ──────────────────────────────────────────────────────────────────────────────

class TestPennySchema:
    @patch("scrapers.penny.time.sleep")
    @patch("scrapers.penny.requests.get")
    @patch("scrapers.penny.date")
    def test_penny_product_schema(self, mock_date, mock_get, mock_sleep, tmp_workdir):
        from datetime import date as real_date
        mock_date.today.return_value = real_date(2026, 3, 27)
        mock_date.side_effect = lambda *a, **kw: real_date(*a, **kw)

        offers_resp = MagicMock()
        offers_resp.status_code = 200
        offers_resp.text = make_penny_offers_html([(25, 3)])
        offers_resp.raise_for_status = MagicMock()

        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = make_billa_api_response(SAMPLE_BILLA_PRODUCTS)
        api_resp.raise_for_status = MagicMock()

        def route_get(url, **kwargs):
            if "angebote" in url and "api" not in url:
                return offers_resp
            return api_resp

        mock_get.side_effect = route_get

        from scrapers.penny import scrape_penny
        products = scrape_penny()

        assert len(products) >= 1
        for p in products:
            _validate_product(p, "penny")
            assert p["inPromotion"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Spar
# ──────────────────────────────────────────────────────────────────────────────

class TestSparSchema:
    @patch("scrapers.spar.CATEGORIES", ["obst-gemuese"])
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar.async_playwright")
    def test_spar_product_schema(self, mock_pw, mock_load_page, tmp_workdir):
        page = make_spar_mock_page(SAMPLE_SPAR_TILES, "1 von 1")
        browser = make_spar_mock_browser([page])

        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=MagicMock(chromium=MagicMock(
            launch=AsyncMock(return_value=browser)
        )))
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pw.return_value = ctx_manager

        from scrapers.spar import scrape_spar
        products = scrape_spar()

        assert len(products) == 3
        for p in products:
            _validate_product(p, "spar")
            assert "amount" in p  # spar-specific extra key


# ──────────────────────────────────────────────────────────────────────────────
# Hofer
# ──────────────────────────────────────────────────────────────────────────────

class TestHoferSchema:
    @patch("scrapers.hofer.requests.get")
    def test_hofer_product_schema(self, mock_get, tmp_workdir):
        resp = MagicMock()
        resp.json.return_value = make_hofer_api_response(SAMPLE_HOFER_API_ITEMS)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        from scrapers.hofer import scrape_hofer
        products = scrape_hofer()

        assert len(products) == len(SAMPLE_HOFER_API_ITEMS)
        for p in products:
            _validate_product(p, "hofer")
            assert "amount" in p  # hofer-specific extra key


# ──────────────────────────────────────────────────────────────────────────────
# Cross-scraper consistency
# ──────────────────────────────────────────────────────────────────────────────

class TestCrossScraperConsistency:
    """Verify the required-key set is identical across all scrapers."""

    @patch("scrapers.billa.CATEGORIES", ["obst-und-gemuese-13751"])
    @patch("scrapers.billa.requests.get")
    def _get_billa_products(self, mock_get, tmp_workdir):
        resp = MagicMock()
        resp.json.return_value = make_billa_api_response(SAMPLE_BILLA_PRODUCTS)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        from scrapers.billa import scrape_billa
        return scrape_billa()

    def test_all_scrapers_share_required_keys(self):
        """Every scraper must produce each key in REQUIRED_PRODUCT_KEYS."""
        # Instead of running all scrapers (complex mock setup), verify by
        # constructing one product per scraper from the parse functions directly.
        from scrapers.billa import _parse_product as _billa_parse
        from scrapers.penny import _parse_product as _penny_parse
        from scrapers.hofer import _parse_product as _hofer_parse
        from scrapers.hofer_flugblatt import _build_product as _flugblatt_build

        products = {
            # Billa and Penny share the same product-discovery API shape.
            "billa": _billa_parse(SAMPLE_BILLA_PRODUCTS[0]),
            "penny": _penny_parse(SAMPLE_BILLA_PRODUCTS[0]),
            "hofer": _hofer_parse(SAMPLE_HOFER_API_ITEMS[0]),
            "hofer_flugblatt": _flugblatt_build(
                {
                    "name": "Emmentaler Scheiben", "brand": "Milsani",
                    "price": 4.99, "originalPrice": 7.49, "amount": "250 g",
                    "unitPrice": 19.96, "unitLabel": "kg",
                    "promotionText": "-33%", "category": "Milchprodukte",
                },
                "2026-07-10", "2026-07-16",
            ),
        }

        for label, product in products.items():
            assert product is not None, f"{label} parse returned None"
            missing = REQUIRED_PRODUCT_KEYS - set(product)
            assert not missing, f"{label} missing keys: {missing}"
