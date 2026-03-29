import json
from unittest.mock import patch, MagicMock

import pytest

from scrapers.lidl import _parse_product, _parse_base_price, _extract_promo_prefix, _scrape_category, scrape_lidl


# ---------------------------------------------------------------------------
# _parse_base_price
# ---------------------------------------------------------------------------

class TestParseBasePrice:
    def test_kg_price(self):
        unit_price, label = _parse_base_price("Je 50 g (1 kg = 19.80)")
        assert unit_price == 19.80
        assert label == "€/kg"

    def test_liter_price(self):
        unit_price, label = _parse_base_price("Je 0,75 l (1 l = 4.65)")
        assert unit_price == 4.65
        assert label == "€/l"

    def test_ab_stk_with_kg(self):
        unit_price, label = _parse_base_price("Ab 2 Stk. je 180 g (1 kg = 5.50)")
        assert unit_price == 5.50
        assert label == "€/kg"

    def test_ab_stk_with_liter(self):
        unit_price, label = _parse_base_price("Ab 12 Stk. je 400 ml (1 l = 1.98)")
        assert unit_price == 1.98
        assert label == "€/l"

    def test_abtropfgewicht(self):
        unit_price, label = _parse_base_price("Ab 12 Stk. je 425 ml (1 kg Abtr. G. = 1.92)")
        assert unit_price == 1.92
        assert label == "€/kg"

    def test_je_kg_no_price(self):
        unit_price, label = _parse_base_price("Je kg")
        assert unit_price is None
        assert label == "€/kg"

    def test_je_stk_no_price(self):
        unit_price, label = _parse_base_price("Je Stk.")
        assert unit_price is None
        assert label == "€/Stk"

    def test_multiplier_format(self):
        unit_price, label = _parse_base_price("10x 20 g (1 kg = 14.95)")
        assert unit_price == 14.95
        assert label == "€/kg"

    def test_empty_returns_none(self):
        assert _parse_base_price("") == (None, None)
        assert _parse_base_price(None) == (None, None)


# ---------------------------------------------------------------------------
# _extract_promo_prefix
# ---------------------------------------------------------------------------

class TestExtractPromoPrefix:
    def test_ab_2_stk(self):
        assert _extract_promo_prefix("Ab 2 Stk. je 180 g (1 kg = 5.50)") == "Ab 2 Stk."

    def test_ab_3_stk(self):
        assert _extract_promo_prefix("Ab 3 Stk. je 200 g (1 kg = 3.95)") == "Ab 3 Stk."

    def test_ab_12_stk(self):
        assert _extract_promo_prefix("Ab 12 Stk. je 0,33 l (0,5 l = 1.09)") == "Ab 12 Stk."

    def test_ab_2_fl(self):
        assert _extract_promo_prefix("Ab 2 Fl. je 0,75 l (1 l = 6.49)") == "Ab 2 Fl."

    def test_je_returns_none(self):
        assert _extract_promo_prefix("Je 50 g (1 kg = 19.80)") is None

    def test_empty_returns_none(self):
        assert _extract_promo_prefix("") is None
        assert _extract_promo_prefix(None) is None


# ---------------------------------------------------------------------------
# _parse_product
# ---------------------------------------------------------------------------

class TestParseProduct:
    def _make_item(self, **overrides):
        """Build a minimal valid API item dict."""
        data = {
            "productId": 10045677,
            "erpNumber": "10045677",
            "fullTitle": "Favorina Mini Ostersortiment",
            "brand": {"name": "Favorina", "url": "/q/search?q=favorina", "showBrand": True},
            "price": {
                "price": 0.99,
                "oldPrice": 0.0,
                "basePrice": {"prefix": False, "text": "Je 50 g (1 kg = 19.80)"},
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
            "image": "https://imgproxy-retcat.assets.schwarz/test.png",
            "category": "Food",
        }
        data.update(overrides)
        return {
            "gridbox": {
                "data": data,
                "meta": {
                    "wonCategoryBreadcrumbs": [
                        [
                            {"id": "10068374", "name": "Essen & Trinken"},
                            {"id": "10071044", "name": "Snacks & Süßigkeiten"},
                        ]
                    ]
                },
            }
        }

    def test_full_product(self):
        item = self._make_item()
        result = _parse_product(item)
        assert result is not None
        assert result["id"] == "lidl_10045677"
        assert result["name"] == "Favorina Mini Ostersortiment"
        assert result["price"] == 0.99
        assert result["originalPrice"] is None  # oldPrice 0.0 → None
        assert result["promotionText"] is None
        assert result["unitPrice"] == 19.80
        assert result["unitLabel"] == "€/kg"
        assert result["category"] == "Snacks & Süßigkeiten"
        assert result["brand"] == "Favorina"
        assert result["sku"] == "10045677"
        assert result["inPromotion"] is True  # all products on this page are promotions
        assert result["imageUrl"] == "https://imgproxy-retcat.assets.schwarz/test.png"
        assert result["supermarket"] == "lidl"

    def test_discounted_product(self):
        item = self._make_item(
            price={
                "price": 1.49,
                "oldPrice": 2.99,
                "discount": {
                    "discountText": "-50%",
                    "percentageDiscount": 50,
                    "showDiscount": True,
                },
                "basePrice": {"prefix": False, "text": "Je 150 g (1 kg = 9.93)"},
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
        )
        result = _parse_product(item)
        assert result is not None
        assert result["price"] == 1.49
        assert result["originalPrice"] == 2.99
        assert result["promotionText"] == "-50%"
        assert result["inPromotion"] is True

    def test_product_without_price_returns_none(self):
        item = self._make_item(
            price={
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
            lidlPlus=[],
        )
        result = _parse_product(item)
        assert result is None

    def test_lidl_plus_product(self):
        """Products where price is only in the lidlPlus array."""
        item = self._make_item(
            price={
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
            lidlPlus=[{
                "price": {
                    "price": 0.49,
                    "basePrice": {"prefix": False, "text": "Je Stk."},
                    "discount": {
                        "deletedPrice": 0.89,
                        "discountText": "-44%",
                        "showDiscount": True,
                    },
                    "displayedCurrency": "€",
                    "hasStar": True,
                    "hasVat": False,
                    "specialTaxes": [],
                },
                "lidlPlusText": "mit Lidl Plus",
            }],
        )
        result = _parse_product(item)
        assert result is not None
        assert result["price"] == 0.49
        assert result["originalPrice"] == 0.89
        assert result["promotionText"] == "-44%, mit Lidl Plus"
        assert result["inPromotion"] is True

    def test_lidl_plus_no_discount(self):
        """Lidl Plus product without a discount, just a special price."""
        item = self._make_item(
            price={
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
            lidlPlus=[{
                "price": {
                    "price": 2.79,
                    "basePrice": {"prefix": False, "text": "Je 150 g (1 kg = 18.60)"},
                    "displayedCurrency": "€",
                    "hasStar": True,
                    "hasVat": False,
                    "specialTaxes": [],
                },
                "lidlPlusText": "mit Lidl Plus",
            }],
        )
        result = _parse_product(item)
        assert result is not None
        assert result["price"] == 2.79
        assert result["originalPrice"] is None
        assert result["promotionText"] == "mit Lidl Plus"
        assert result["inPromotion"] is True

    def test_promo_with_ab_stk_and_discount(self):
        """Granatapfel-style: 1+1 gratis + Ab 2 Stk."""
        item = self._make_item(
            price={
                "price": 1.39,
                "oldPrice": 0.0,
                "discount": {
                    "discountText": "1+1 gratis",
                    "showDiscount": False,
                },
                "basePrice": {"prefix": False, "text": "Ab 2 Stk. je"},
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
        )
        result = _parse_product(item)
        assert result is not None
        assert result["price"] == 1.39
        assert result["originalPrice"] is None
        assert result["promotionText"] == "1+1 gratis, Ab 2 Stk."
        assert result["inPromotion"] is True

    def test_promo_ab_stk_only(self):
        """Product with only 'Ab X Stk.' promo, no discount text."""
        item = self._make_item(
            price={
                "price": 0.44,
                "oldPrice": 0.0,
                "basePrice": {"prefix": False, "text": "Ab 2 Stk. je 250 g (1 kg = 1.76)"},
                "currencyCode": "EUR",
                "currencySymbol": "€",
                "displayedCurrency": "€",
                "hasStar": True,
                "hasVat": False,
                "specialTaxes": [],
                "variantsHaveDifferentPrices": False,
            },
        )
        result = _parse_product(item)
        assert result is not None
        assert result["promotionText"] == "Ab 2 Stk."
        assert result["inPromotion"] is True

    def test_product_no_brand(self):
        item = self._make_item(brand=None)
        result = _parse_product(item)
        assert result is not None
        assert result["brand"] is None

    def test_product_no_image(self):
        item = self._make_item(image=None)
        result = _parse_product(item)
        assert result is not None
        assert result["imageUrl"] is None

    def test_product_empty_breadcrumbs_uses_category_field(self):
        item = self._make_item()
        item["gridbox"]["meta"]["wonCategoryBreadcrumbs"] = [[]]
        result = _parse_product(item)
        assert result is not None
        assert result["category"] == "Food"


# ---------------------------------------------------------------------------
# _scrape_category (mocked HTTP)
# ---------------------------------------------------------------------------

class TestScrapeCategory:
    @patch("scrapers.lidl.requests.get")
    @patch("scrapers.lidl.time.sleep")
    def test_single_page(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "numFound": 1,
            "items": [
                {
                    "gridbox": {
                        "data": {
                            "productId": 123,
                            "erpNumber": "123",
                            "fullTitle": "Apfel",
                            "price": {"price": 1.99, "oldPrice": 0.0},
                            "image": "https://example.com/img.png",
                            "category": "Food",
                        },
                        "meta": {"wonCategoryBreadcrumbs": [[{"id": "1", "name": "Obst"}]]},
                    }
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        products = _scrape_category("10068374")
        assert len(products) == 1
        assert products[0]["name"] == "Apfel"
        mock_sleep.assert_not_called()

    @patch("scrapers.lidl.requests.get")
    @patch("scrapers.lidl.time.sleep")
    def test_pagination(self, mock_sleep, mock_get):
        def _make_response(items, num_found):
            r = MagicMock()
            r.json.return_value = {"numFound": num_found, "items": items}
            r.raise_for_status = MagicMock()
            return r

        item_template = lambda pid: {
            "gridbox": {
                "data": {
                    "productId": pid,
                    "erpNumber": str(pid),
                    "fullTitle": f"P{pid}",
                    "price": {"price": 1.0, "oldPrice": 0.0},
                    "image": None,
                    "category": "Food",
                },
                "meta": {"wonCategoryBreadcrumbs": [[{"id": "1", "name": "Cat"}]]},
            }
        }

        mock_get.side_effect = [
            _make_response([item_template(1)], 2),
            _make_response([item_template(2)], 2),
        ]

        products = _scrape_category("test")
        assert len(products) == 2
        mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# scrape_lidl (mocked)
# ---------------------------------------------------------------------------

class TestScrapeLidl:
    @patch("scrapers.lidl._scrape_category")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.lidl.json.dump")
    def test_scrape_lidl_aggregates(self, mock_dump, mock_open, mock_scrape):
        mock_scrape.return_value = [
            {"sku": "123", "name": "P1", "price": 1.0, "supermarket": "lidl"}
        ]
        result = scrape_lidl()
        assert len(result) == 1
        assert mock_scrape.call_count == 1
        mock_dump.assert_called_once()

    @patch("scrapers.lidl._scrape_category")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("scrapers.lidl.json.dump")
    def test_scrape_lidl_handles_error(self, mock_dump, mock_open, mock_scrape):
        mock_scrape.side_effect = Exception("Network error")
        result = scrape_lidl()
        assert len(result) == 0
