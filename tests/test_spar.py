import pytest

from scrapers.spar import _extract_sku, _parse_unit_price_text


# ---------------------------------------------------------------------------
# _extract_sku
# ---------------------------------------------------------------------------

class TestExtractSku:
    def test_valid_url(self):
        url = "https://assets.spar.at/at/2020005521308/HB_500px.jpg"
        assert _extract_sku(url) == "2020005521308"

    def test_different_sku(self):
        url = "https://assets.spar.at/at/1234567890123/image.jpg"
        assert _extract_sku(url) == "1234567890123"

    def test_no_match(self):
        url = "https://example.com/image.jpg"
        assert _extract_sku(url) is None

    def test_none_input(self):
        assert _extract_sku(None) is None

    def test_empty_string(self):
        assert _extract_sku("") is None


# ---------------------------------------------------------------------------
# _parse_unit_price_text
# ---------------------------------------------------------------------------

class TestParseUnitPriceText:
    def test_per_kg(self):
        price, unit = _parse_unit_price_text("Per 1 kg 19,95")
        assert price == 19.95
        assert unit == "kg"

    def test_per_liter(self):
        price, unit = _parse_unit_price_text("Per 1 l 2,50")
        assert price == 2.50
        assert unit == "l"

    def test_per_100g(self):
        price, unit = _parse_unit_price_text("Per 100 g. 0,99")
        assert price == 0.99
        assert unit == "g"

    def test_none_input(self):
        price, unit = _parse_unit_price_text(None)
        assert price is None
        assert unit is None

    def test_empty_string(self):
        price, unit = _parse_unit_price_text("")
        assert price is None
        assert unit is None

    def test_no_match(self):
        price, unit = _parse_unit_price_text("some random text")
        assert price is None
        assert unit is None

    def test_dot_stripped_from_unit(self):
        price, unit = _parse_unit_price_text("Per 1 kg. 5,00")
        assert price == 5.00
        assert unit == "kg"
