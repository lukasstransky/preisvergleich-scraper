import json
from unittest.mock import patch, MagicMock

import pytest

from scrapers.billa import _parse_product, _scrape_category, scrape_billa


# ---------------------------------------------------------------------------
# _parse_product
# ---------------------------------------------------------------------------

class TestParseProduct:
    def test_full_product(self):
        product = {
            "sku": "00-123456",
            "name": "Testprodukt",
            "price": {
                "regular": {
                    "value": 299,
                    "perStandardizedQuantity": 598,
                    "promotionText": "-25%",
                },
                "crossed": 399,
                "baseUnitShort": "€/kg",
            },
            "category": "obst-und-gemuese-13751",
            "brand": {"name": "TestBrand"},
            "inPromotion": True,
            "images": ["https://img.example.com/product.jpg"],
        }
        result = _parse_product(product)
        assert result is not None
        assert result["id"] == "billa_00-123456"
        assert result["name"] == "Testprodukt"
        assert result["price"] == 2.99
        assert result["originalPrice"] == 3.99
        assert result["promotionText"] == "-25%"
        assert result["unitPrice"] == 5.98
        assert result["unitLabel"] == "€/kg"
        assert result["category"] == "obst-und-gemuese-13751"
        assert result["brand"] == "TestBrand"
        assert result["sku"] == "00-123456"
        assert result["inPromotion"] is True
        assert result["imageUrl"] == "https://img.example.com/product.jpg"
        assert result["supermarket"] == "billa"

    def test_product_without_optional_fields(self):
        product = {
            "sku": "00-999",
            "name": "Einfaches Produkt",
            "price": {
                "regular": {"value": 150},
            },
            "category": "getraenke-13784",
        }
        result = _parse_product(product)
        assert result is not None
        assert result["price"] == 1.50
        assert result["originalPrice"] is None
        assert result["unitPrice"] is None
        assert result["unitLabel"] is None
        assert result["brand"] is None
        assert result["imageUrl"] is None
        assert result["inPromotion"] is False
        assert result["promotionText"] is None

    def test_product_missing_price_key_returns_none(self):
        product = {"sku": "00-111", "name": "Broken"}
        assert _parse_product(product) is None

    def test_product_missing_regular_price_returns_none(self):
        product = {"sku": "00-222", "name": "Broken", "price": {}}
        assert _parse_product(product) is None

    def test_product_no_brand_object(self):
        product = {
            "sku": "00-333",
            "name": "NoBrand",
            "price": {"regular": {"value": 100}},
            "brand": None,
        }
        result = _parse_product(product)
        assert result is not None
        assert result["brand"] is None

    def test_product_empty_images(self):
        product = {
            "sku": "00-444",
            "name": "NoImage",
            "price": {"regular": {"value": 200}},
            "images": [],
        }
        result = _parse_product(product)
        assert result is not None
        assert result["imageUrl"] is None


# ---------------------------------------------------------------------------
# _scrape_category (mocked HTTP)
# ---------------------------------------------------------------------------

class TestScrapeCategory:
    @patch("scrapers.billa.requests.get")
    @patch("scrapers.billa.time.sleep")
    def test_single_page(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "sku": "00-1",
                    "name": "Apfel",
                    "price": {"regular": {"value": 199}},
                }
            ],
            "offset": 0,
            "count": 1,
            "total": 1,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        products = _scrape_category("obst-und-gemuese-13751")
        assert len(products) == 1
        assert products[0]["name"] == "Apfel"
        mock_sleep.assert_not_called()

    @patch("scrapers.billa.requests.get")
    @patch("scrapers.billa.time.sleep")
    def test_pagination(self, mock_sleep, mock_get):
        page0_response = MagicMock()
        page0_response.json.return_value = {
            "results": [{"sku": "00-1", "name": "P1", "price": {"regular": {"value": 100}}}],
            "offset": 0,
            "count": 1,
            "total": 2,
        }
        page0_response.raise_for_status = MagicMock()

        page1_response = MagicMock()
        page1_response.json.return_value = {
            "results": [{"sku": "00-2", "name": "P2", "price": {"regular": {"value": 200}}}],
            "offset": 1,
            "count": 1,
            "total": 2,
        }
        page1_response.raise_for_status = MagicMock()

        mock_get.side_effect = [page0_response, page1_response]

        products = _scrape_category("test-category")
        assert len(products) == 2
        mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# scrape_billa (mocked)
# ---------------------------------------------------------------------------

class TestScrapeBilla:
    @patch("scrapers.billa._scrape_category")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.billa.json.dump")
    def test_scrape_billa_aggregates_categories(self, mock_dump, mock_open, mock_scrape):
        mock_scrape.return_value = [
            {"sku": "00-1", "name": "P1", "price": 1.0, "supermarket": "billa"}
        ]

        result = scrape_billa()
        # 15 categories in CATEGORIES list
        assert len(result) == 15
        assert mock_scrape.call_count == 15
        mock_dump.assert_called_once()

    @patch("scrapers.billa._scrape_category")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.billa.json.dump")
    def test_scrape_billa_handles_category_error(self, mock_dump, mock_open, mock_scrape):
        mock_scrape.side_effect = Exception("Network error")
        result = scrape_billa()
        assert len(result) == 0
