import pytest

from scrapers.hofer import _parse_comparison_price, _parse_was_price, _parse_product


# ---------------------------------------------------------------------------
# _parse_comparison_price
# ---------------------------------------------------------------------------

class TestParseComparisonPrice:
    def test_full_kg(self):
        price, label = _parse_comparison_price("(€ 1,88/1 kg)")
        assert price == 1.88
        assert label == "kg"

    def test_liter(self):
        price, label = _parse_comparison_price("(€ 2,50/1 l)")
        assert price == 2.50
        assert label == "l"

    def test_none_input(self):
        price, label = _parse_comparison_price(None)
        assert price is None
        assert label is None

    def test_empty_string(self):
        price, label = _parse_comparison_price("")
        assert price is None
        assert label is None

    def test_no_unit(self):
        price, label = _parse_comparison_price("(€ 0,94/Stk)")
        assert price == 0.94
        assert label == "Stk"


# ---------------------------------------------------------------------------
# _parse_was_price
# ---------------------------------------------------------------------------

class TestParseWasPrice:
    def test_basic(self):
        assert _parse_was_price("€ 1,89") == 1.89

    def test_with_space(self):
        assert _parse_was_price("€  2,99") == 2.99

    def test_none(self):
        assert _parse_was_price(None) is None

    def test_empty(self):
        assert _parse_was_price("") is None


# ---------------------------------------------------------------------------
# _parse_product
# ---------------------------------------------------------------------------

class TestParseProduct:
    def _make_item(self, **overrides):
        base = {
            "sku": "000000000000100778",
            "name": "Toastbrot",
            "brandName": "HAPPY HARVEST",
            "urlSlugText": "happy-harvest-toastbrot",
            "sellingSize": "0,5 kg",
            "price": {
                "amountRelevant": 94,
                "comparisonDisplay": "(€ 1,88/1 kg)",
                "wasPriceDisplay": None,
            },
            "categories": [
                {"id": "158816141856710104", "name": "Brot und Backwaren"},
            ],
            "assets": [],
        }
        base.update(overrides)
        return base

    def test_id_format(self):
        p = _parse_product(self._make_item())
        assert p["id"] == "hofer_000000000000100778"

    def test_price_converted_from_cents(self):
        p = _parse_product(self._make_item())
        assert p["price"] == pytest.approx(0.94)

    def test_brand_from_api(self):
        p = _parse_product(self._make_item())
        assert p["brand"] == "HAPPY HARVEST"

    def test_unit_price_parsed(self):
        p = _parse_product(self._make_item())
        assert p["unitPrice"] == pytest.approx(1.88)
        assert p["unitLabel"] == "kg"

    def test_not_in_promotion_without_was_price(self):
        p = _parse_product(self._make_item())
        assert p["inPromotion"] is False

    def test_in_promotion_with_was_price(self):
        item = self._make_item()
        item["price"]["wasPriceDisplay"] = "€ 1,29"
        p = _parse_product(item)
        assert p["inPromotion"] is True
        assert p["originalPrice"] == pytest.approx(1.29)

    def test_preiswochen_marked_as_promotion(self):
        item = self._make_item()
        item["categories"] = [{"id": "1588161434751158", "name": "HOFER PREISWOCHEN"}]
        p = _parse_product(item)
        assert p["inPromotion"] is True
        assert p["promotionText"] == "Preiswoche"

    def test_product_url(self):
        p = _parse_product(self._make_item())
        assert p["productUrl"] == "https://www.hofer.at/produkt/happy-harvest-toastbrot-000000000000100778"

    def test_normalized_category(self):
        p = _parse_product(self._make_item())
        assert p["normalizedCategory"] == "Brot & Gebäck"

    def test_supermarket_field(self):
        p = _parse_product(self._make_item())
        assert p["supermarket"] == "hofer"
