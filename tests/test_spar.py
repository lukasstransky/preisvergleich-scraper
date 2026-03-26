import hashlib

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

    def test_placeholder_image_url(self):
        """Placeholder images without a numeric SKU should return None."""
        url = "https://cdn1.interspar.at/cachableservlets/graficImage.dam/at/produktweltBIO/HB_105px.png"
        assert _extract_sku(url) is None

    def test_product_link_url(self):
        """SKU can be extracted from a product page link."""
        url = "/produkte/spar-premium-batavia-rot-300g-2020005521308/"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_url_with_query(self):
        url = "/produkte/spar-premium-xyz-2020005521308?page=2"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_url_slash_separated(self):
        url = "/onlineshop/r/some-name/p/2020005521308"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_with_p_prefix(self):
        """SKU preceded by '-p' in produktwelt URLs."""
        url = "/produktwelt/spar-premium-weinviertler-beilagen-erdaepfel-vorwiegend-festkochend-p2020003543821"
        assert _extract_sku(url) == "2020003543821"

    def test_product_link_with_p_prefix_and_trailing_slash(self):
        url = "/produktwelt/spar-natur-pur-bio-apfel-p2020004977113/"
        assert _extract_sku(url) == "2020004977113"

    def test_cdn_image_url(self):
        """CDN image URLs from interspar.at."""
        url = "https://cdn1.interspar.at/cachableservlets/articleImage.dam/at/2020004977113/HB_500px.jpg"
        assert _extract_sku(url) == "2020004977113"

    def test_cdn_image_url_short_sku(self):
        url = "https://cdn1.interspar.at/cachableservlets/articleImage.dam/at/6737634/HB_500px.jpg"
        assert _extract_sku(url) == "6737634"

    def test_p_prefix_not_greedy(self):
        """Only one 'p' should be stripped, not part of the SKU."""
        url = "/produktwelt/some-product-p1234567"
        assert _extract_sku(url) == "1234567"


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


# ---------------------------------------------------------------------------
# Fallback hash ID
# ---------------------------------------------------------------------------

class TestFallbackHashId:
    """Verify that the hash-based fallback ID is stable and deterministic."""

    def _make_hash_id(self, brand, name, category):
        hash_input = f"{brand}|{name}|{category}".lower()
        return f"spar_hash_{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"

    def test_deterministic(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        assert id1 == id2

    def test_different_products_differ(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("SPAR", "Bio Birnen", "obst-gemuese")
        assert id1 != id2

    def test_case_insensitive(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("spar", "bio äpfel", "obst-gemuese")
        assert id1 == id2

    def test_prefix(self):
        fid = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        assert fid.startswith("spar_hash_")
        assert len(fid) == len("spar_hash_") + 12
