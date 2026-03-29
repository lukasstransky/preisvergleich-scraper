"""Tests for scrapers.tokenizer – search-token generation."""

import pytest

from scrapers.tokenizer import tokenize_name


class TestTokenizeName:
    """Core tokenization logic."""

    def test_simple_name(self):
        assert tokenize_name("Vollmilch") == ["vollmilch"]

    def test_multi_word(self):
        assert tokenize_name("Bio Vollmilch 3.5%") == ["bio", "vollmilch"]

    def test_hyphenated_name(self):
        tokens = tokenize_name("Bio-Vollmilch")
        assert tokens == ["bio", "vollmilch"]

    def test_german_umlauts(self):
        tokens = tokenize_name("Müsli Nüsse Größe")
        assert "müsli" in tokens
        assert "nüsse" in tokens
        assert "größe" in tokens

    def test_brand_prefix(self):
        tokens = tokenize_name("Ja! Natürlich Bio-Vollmilch")
        assert tokens == ["ja", "natürlich", "bio", "vollmilch"]

    def test_deduplication(self):
        tokens = tokenize_name("Milch Milch Milch")
        assert tokens == ["milch"]

    def test_preserves_order(self):
        tokens = tokenize_name("Apfel Birne Kirsche")
        assert tokens == ["apfel", "birne", "kirsche"]

    def test_filters_short_tokens(self):
        """Single-character tokens (like 'l' from '1L') are dropped."""
        tokens = tokenize_name("Milch 3.5% 1L")
        assert "milch" in tokens
        assert "l" not in tokens  # too short

    def test_numeric_tokens_kept_when_long_enough(self):
        """Tokens like '100g' are kept because they're ≥ 2 chars."""
        tokens = tokenize_name("Milchschokolade Vollmilch 100g")
        assert "100g" in tokens

    def test_none_input(self):
        assert tokenize_name(None) == []

    def test_empty_string(self):
        assert tokenize_name("") == []

    def test_whitespace_only(self):
        assert tokenize_name("   ") == []

    def test_case_insensitive(self):
        tokens = tokenize_name("MILCH Milch milch")
        assert tokens == ["milch"]


class TestTokenizeNameEdgeCases:
    """Edge cases and real-world product names."""

    def test_product_with_percentage(self):
        tokens = tokenize_name("Bergbauern Milch 3,5% 1L")
        assert "bergbauern" in tokens
        assert "milch" in tokens

    def test_multipack(self):
        tokens = tokenize_name("Joghurt Natur 6x180g")
        assert "joghurt" in tokens
        assert "natur" in tokens
        assert "6x180g" in tokens

    def test_special_characters_stripped(self):
        tokens = tokenize_name("Dr. Oetker Vanille-Pudding")
        assert "dr" in tokens
        assert "oetker" in tokens
        assert "vanille" in tokens
        assert "pudding" in tokens

    def test_slash_separated(self):
        tokens = tokenize_name("Butter/Margarine")
        assert "butter" in tokens
        assert "margarine" in tokens

    def test_real_product_milchschokolade(self):
        """The motivating use case: 'Milch' should NOT appear in tokens
        for 'Milchschokolade' – only the full compound word does."""
        tokens = tokenize_name("Milka Milchschokolade 100g")
        assert "milchschokolade" in tokens
        assert "milka" in tokens
        # "milch" as a standalone token should NOT be present
        assert "milch" not in tokens

    def test_real_product_pure_milk(self):
        """For actual milk products, 'milch' IS a standalone token."""
        tokens = tokenize_name("Milch frisch 3,5% 1L")
        assert "milch" in tokens
        assert "frisch" in tokens


class TestTokenizeNameInScrapers:
    """Verify that scraper parse functions include nameTokens."""

    def test_billa_parse_includes_tokens(self):
        from scrapers.billa import _parse_product

        product = {
            "sku": "00-123456",
            "name": "Bio Vollmilch",
            "price": {"regular": {"value": 149}},
            "category": "kuehlwaren",
        }
        result = _parse_product(product)
        assert result is not None
        assert "nameTokens" in result
        assert result["nameTokens"] == ["bio", "vollmilch"]

    def test_penny_parse_includes_tokens(self):
        from scrapers.penny import _parse_product

        product = {
            "sku": "99-001",
            "name": "Schoko Milchschnitte",
            "price": {"regular": {"value": 199}},
            "category": "kuehlwaren",
        }
        result = _parse_product(product)
        assert result is not None
        assert "nameTokens" in result
        assert result["nameTokens"] == ["schoko", "milchschnitte"]

    def test_lidl_parse_includes_tokens(self):
        from scrapers.lidl import _parse_product

        item = {
            "gridbox": {
                "data": {
                    "fullTitle": "Milka Alpenmilch Schokolade",
                    "price": {"price": 1.29},
                    "productId": "12345",
                    "category": "Süßwaren",
                    "brand": {"name": "Milka"},
                    "image": "https://example.com/img.jpg",
                }
            }
        }
        result = _parse_product(item)
        assert result is not None
        assert "nameTokens" in result
        assert "milka" in result["nameTokens"]
        assert "alpenmilch" in result["nameTokens"]
        assert "schokolade" in result["nameTokens"]

    def test_none_name_produces_empty_tokens(self):
        from scrapers.billa import _parse_product

        product = {
            "sku": "00-999",
            "name": None,
            "price": {"regular": {"value": 100}},
            "category": "test",
        }
        result = _parse_product(product)
        assert result is not None
        assert result["nameTokens"] == []
