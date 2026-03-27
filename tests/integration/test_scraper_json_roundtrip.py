"""Integration: scraper → JSON file roundtrip.

Each test runs a real scraper function with transport-level mocks, then
reads the resulting JSON file from disk and validates it matches the
returned product list and passes schema checks.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import REQUIRED_PRODUCT_KEYS, OPTIONAL_PRODUCT_KEYS
from tests.integration.helpers import (
    SAMPLE_BILLA_PRODUCTS,
    SAMPLE_SPAR_TILES,
    SAMPLE_HOFER_TILES,
    make_billa_api_response,
    make_billa_api_product,
    make_penny_offers_html,
    make_spar_mock_page,
    make_spar_mock_browser,
    make_hofer_mock_page,
    make_hofer_mock_browser,
)

pytestmark = pytest.mark.integration


def _assert_valid_schema(product, supermarket):
    keys = set(product.keys())
    missing = REQUIRED_PRODUCT_KEYS - keys
    extra = keys - REQUIRED_PRODUCT_KEYS - OPTIONAL_PRODUCT_KEYS
    assert not missing, f"Missing keys {missing} in {product.get('id')}"
    assert not extra, f"Unexpected keys {extra} in {product.get('id')}"
    assert product["supermarket"] == supermarket
    assert product["id"].startswith(f"{supermarket}_")


# ──────────────────────────────────────────────────────────────────────────────
# Billa
# ──────────────────────────────────────────────────────────────────────────────

class TestBillaJsonRoundtrip:
    @patch("scrapers.billa.CATEGORIES", ["obst-und-gemuese-13751"])
    @patch("scrapers.billa.requests.get")
    def test_billa_writes_valid_json(self, mock_get, tmp_workdir):
        resp = MagicMock()
        resp.json.return_value = make_billa_api_response(SAMPLE_BILLA_PRODUCTS)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        from scrapers.billa import scrape_billa
        products = scrape_billa()

        json_path = tmp_workdir / "billa.json"
        assert json_path.exists(), "billa.json was not written"

        with open(json_path, "r", encoding="utf-8") as f:
            file_products = json.load(f)

        assert len(file_products) == len(products)
        assert file_products == products

        for p in file_products:
            _assert_valid_schema(p, "billa")

    @patch("scrapers.billa.CATEGORIES", ["obst-und-gemuese-13751", "brot-und-gebaeck-15520"])
    @patch("scrapers.billa.requests.get")
    def test_billa_multiple_categories(self, mock_get, tmp_workdir):
        """Products from multiple categories end up in a single JSON file."""
        products_cat1 = [make_billa_api_product("00-200001", "Apfel", 199, category="Obst")]
        products_cat2 = [make_billa_api_product("00-200002", "Brot", 349, category="Brot")]

        call_count = {"n": 0}

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if call_count["n"] == 0:
                resp.json.return_value = make_billa_api_response(products_cat1)
            else:
                resp.json.return_value = make_billa_api_response(products_cat2)
            call_count["n"] += 1
            return resp

        mock_get.side_effect = side_effect

        from scrapers.billa import scrape_billa
        products = scrape_billa()

        assert len(products) == 2
        with open(tmp_workdir / "billa.json", "r", encoding="utf-8") as f:
            file_products = json.load(f)
        assert len(file_products) == 2
        categories = {p["category"] for p in file_products}
        assert categories == {"Obst", "Brot"}


# ──────────────────────────────────────────────────────────────────────────────
# Penny
# ──────────────────────────────────────────────────────────────────────────────

class TestPennyJsonRoundtrip:
    @patch("scrapers.penny.time.sleep")
    @patch("scrapers.penny.requests.get")
    @patch("scrapers.penny.date")
    def test_penny_writes_valid_json(self, mock_date, mock_get, mock_sleep, tmp_workdir):
        from datetime import date as real_date
        mock_date.today.return_value = real_date(2026, 3, 27)
        mock_date.side_effect = lambda *a, **kw: real_date(*a, **kw)

        offers_html = make_penny_offers_html([(25, 3)])

        offers_resp = MagicMock()
        offers_resp.text = offers_html
        offers_resp.raise_for_status = MagicMock()

        api_products = [
            make_billa_api_product("00-P001", "Apfel", 199, category="Obst"),
            make_billa_api_product("00-P002", "Banane", 149, category="Obst"),
        ]
        api_resp = MagicMock()
        api_resp.json.return_value = make_billa_api_response(api_products)
        api_resp.raise_for_status = MagicMock()

        def route_get(url, **kwargs):
            if "angebote" in url and "api" not in url:
                return offers_resp
            return api_resp

        mock_get.side_effect = route_get

        from scrapers.penny import scrape_penny
        products = scrape_penny()

        json_path = tmp_workdir / "penny.json"
        assert json_path.exists(), "penny.json was not written"

        with open(json_path, "r", encoding="utf-8") as f:
            file_products = json.load(f)

        assert len(file_products) == len(products)
        assert file_products == products

        for p in file_products:
            _assert_valid_schema(p, "penny")
            assert p["inPromotion"] is True  # all offer products


# ──────────────────────────────────────────────────────────────────────────────
# Spar
# ──────────────────────────────────────────────────────────────────────────────

class TestSparJsonRoundtrip:
    @patch("scrapers.spar.CATEGORIES", ["obst-gemuese"])
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar.async_playwright")
    def test_spar_writes_valid_json(self, mock_pw, mock_load_page, tmp_workdir):
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

        json_path = tmp_workdir / "spar.json"
        assert json_path.exists(), "spar.json was not written"

        with open(json_path, "r", encoding="utf-8") as f:
            file_products = json.load(f)

        assert len(file_products) == len(products)
        assert file_products == products

        for p in file_products:
            _assert_valid_schema(p, "spar")

        # Also check error log was written
        errors_path = tmp_workdir / "spar_errors.json"
        assert errors_path.exists(), "spar_errors.json was not written"
        with open(errors_path, "r", encoding="utf-8") as f:
            error_data = json.load(f)
        assert "errors" in error_data
        assert "timestamp" in error_data


# ──────────────────────────────────────────────────────────────────────────────
# Hofer
# ──────────────────────────────────────────────────────────────────────────────

class TestHoferJsonRoundtrip:
    @patch("scrapers.hofer.CATEGORIES", ["brot-und-backwaren"])
    @patch("scrapers.hofer.sync_playwright")
    def test_hofer_writes_valid_json(self, mock_pw, tmp_workdir):
        cat_page = make_hofer_mock_page(SAMPLE_HOFER_TILES)
        offers_page = make_hofer_mock_page([], offer_links=[])

        browser = make_hofer_mock_browser([cat_page, offers_page])

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock(chromium=MagicMock(
            launch=MagicMock(return_value=browser)
        )))
        ctx.__exit__ = MagicMock(return_value=False)
        mock_pw.return_value = ctx

        from scrapers.hofer import scrape_hofer
        products = scrape_hofer()

        json_path = tmp_workdir / "hofer.json"
        assert json_path.exists(), "hofer.json was not written"

        with open(json_path, "r", encoding="utf-8") as f:
            file_products = json.load(f)

        assert len(file_products) == len(products)
        assert file_products == products

        for p in file_products:
            _assert_valid_schema(p, "hofer")
