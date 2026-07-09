import json
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from scrapers.penny import (
    _parse_product,
    _scrape_category,
    _scrape_offers,
    scrape_penny,
)


# ---------------------------------------------------------------------------
# _parse_product
# ---------------------------------------------------------------------------

class TestParseProduct:
    def test_full_product(self):
        product = {
            "sku": "78-101754",
            "slug": "ottakringer-helles-78101754",
            "name": "Ottakringer Helles",
            "price": {
                "regular": {
                    "value": 135,
                    "perStandardizedQuantity": 270,
                    "promotionText": "-25%",
                },
                "crossed": 179,
                "baseUnitShort": "l",
                "validityStart": "2026-06-18",
                "validityEnd": "2026-06-24",
            },
            "category": "Bier & Radler",
            "brand": {"name": "Ottakringer"},
            "inPromotion": True,
            "images": ["https://img.example.com/product.jpg"],
        }
        result = _parse_product(product)
        assert result is not None
        assert result["id"] == "penny_78-101754"
        assert result["name"] == "Ottakringer Helles"
        assert result["price"] == 1.35
        assert result["originalPrice"] == 1.79
        assert result["promotionText"] == "-25%"
        assert result["unitPrice"] == 2.70
        assert result["unitLabel"] == "l"
        assert result["category"] == "Bier & Radler"
        assert result["brand"] == "Ottakringer"
        assert result["sku"] == "78-101754"
        assert result["inPromotion"] is True
        assert result["imageUrl"] == "https://img.example.com/product.jpg"
        assert result["productUrl"] == "https://www.penny.at/produkte/ottakringer-helles-78101754"
        assert result["offerStart"] == "2026-06-18"
        assert result["offerEnd"] == "2026-06-24"
        assert result["supermarket"] == "penny"

    def test_product_without_optional_fields(self):
        product = {
            "sku": "78-999",
            "name": "Einfaches Produkt",
            "price": {
                "regular": {"value": 150},
            },
            "category": "Grundnahrungsmittel",
        }
        result = _parse_product(product)
        assert result is not None
        assert result["price"] == 1.50
        assert result["originalPrice"] is None
        assert result["unitPrice"] is None
        assert result["unitLabel"] is None
        assert result["brand"] is None
        assert result["imageUrl"] is None
        assert result["productUrl"] is None
        assert result["offerStart"] is None
        assert result["offerEnd"] is None
        assert result["inPromotion"] is False
        assert result["promotionText"] is None

    def test_product_missing_price_key_returns_none(self):
        product = {"sku": "78-111", "name": "Broken"}
        assert _parse_product(product) is None

    def test_product_missing_regular_price_returns_none(self):
        product = {"sku": "78-222", "name": "Broken", "price": {}}
        assert _parse_product(product) is None

    def test_product_no_brand_object(self):
        product = {
            "sku": "78-333",
            "name": "NoBrand",
            "price": {"regular": {"value": 100}},
            "brand": None,
        }
        result = _parse_product(product)
        assert result is not None
        assert result["brand"] is None

    def test_product_empty_images(self):
        product = {
            "sku": "78-444",
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
    @patch("scrapers.penny.requests.get")
    @patch("scrapers.penny.time.sleep")
    def test_single_page(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "sku": "78-1",
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

        products = _scrape_category("obst-und-gemuese-13013")
        assert len(products) == 1
        assert products[0]["name"] == "Apfel"
        mock_sleep.assert_not_called()

    @patch("scrapers.penny.requests.get")
    @patch("scrapers.penny.time.sleep")
    def test_pagination(self, mock_sleep, mock_get):
        page0_response = MagicMock()
        page0_response.json.return_value = {
            "results": [{"sku": "78-1", "name": "P1", "price": {"regular": {"value": 100}}}],
            "offset": 0,
            "count": 1,
            "total": 2,
        }
        page0_response.raise_for_status = MagicMock()

        page1_response = MagicMock()
        page1_response.json.return_value = {
            "results": [{"sku": "78-2", "name": "P2", "price": {"regular": {"value": 200}}}],
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
# _scrape_offers
# ---------------------------------------------------------------------------

def _offer_product(sku, offer_end):
    """Build a raw API product with the given offer end date."""
    return {
        "sku": sku,
        "name": sku,
        "price": {
            "regular": {"value": 100},
            "validityEnd": offer_end,
        },
    }


class TestScrapeOffers:
    @patch("scrapers.penny._scrape_category")
    @patch("scrapers.penny.date")
    def test_drops_expired_keeps_current_and_upcoming(self, mock_date, mock_scrape):
        mock_date.today.return_value = date(2026, 7, 7)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        mock_scrape.return_value = [
            _parse_product(_offer_product("78-1", "2026-07-01")),  # expired → drop
            _parse_product(_offer_product("78-2", "2026-07-08")),  # current → keep
            _parse_product(_offer_product("78-3", "2026-07-15")),  # upcoming → keep
            _parse_product(_offer_product("78-4", None)),          # no end → keep
        ]

        live = _scrape_offers()
        skus = {p["sku"] for p in live}
        assert skus == {"78-2", "78-3", "78-4"}
        assert all(p["inPromotion"] is True for p in live)
        mock_scrape.assert_called_once_with("alle-angebote-99000000")

    @patch("scrapers.penny._scrape_category")
    @patch("scrapers.penny.date")
    def test_keeps_offer_ending_today(self, mock_date, mock_scrape):
        mock_date.today.return_value = date(2026, 7, 7)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        mock_scrape.return_value = [
            _parse_product(_offer_product("78-9", "2026-07-07")),  # ends today → keep
        ]

        live = _scrape_offers()
        assert len(live) == 1


# ---------------------------------------------------------------------------
# scrape_penny (mocked)
# ---------------------------------------------------------------------------

class TestScrapePenny:
    @patch("scrapers.penny._scrape_offers")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.penny.json.dump")
    def test_scrape_penny_writes_offer_products(self, mock_dump, mock_open, mock_offers):
        mock_offers.return_value = [
            {"sku": "78-1", "name": "P1", "price": 1.0, "supermarket": "penny"},
            {"sku": "78-2", "name": "P2", "price": 2.0, "supermarket": "penny"},
        ]

        result = scrape_penny()
        assert len(result) == 2
        mock_dump.assert_called_once()

    @patch("scrapers.penny._scrape_offers")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.penny.json.dump")
    def test_scrape_penny_empty_offers(self, mock_dump, mock_open, mock_offers):
        mock_offers.return_value = []
        result = scrape_penny()
        assert len(result) == 0
        mock_dump.assert_called_once()
