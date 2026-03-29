"""Tests for scrapers.categories – unified category normalization."""

import pytest

from scrapers.categories import (
    normalize_category,
    NORMALIZED_CATEGORIES,
    OBST_GEMUESE,
    BROT_GEBAECK,
    MILCHPRODUKTE,
    FLEISCH_FISCH,
    TIEFKUEHL,
    GETRAENKE,
    SUESSES_SNACKS,
    KAFFEE_TEE,
    GRUNDNAHRUNGSMITTEL,
    FERTIGGERICHTE,
    FRUEHSTUECK_AUFSTRICHE,
    ALKOHOL,
    DROGERIE_HAUSHALT,
    BABY_TIER,
    SONSTIGES,
)


class TestNormalizedCategoriesConstant:
    def test_has_expected_count(self):
        assert len(NORMALIZED_CATEGORIES) == 15

    def test_no_duplicates(self):
        assert len(NORMALIZED_CATEGORIES) == len(set(NORMALIZED_CATEGORIES))

    def test_sonstiges_is_last(self):
        assert NORMALIZED_CATEGORIES[-1] == SONSTIGES


class TestExactMatchSpar:
    """Spar uses URL slugs as categories."""

    @pytest.mark.parametrize("raw,expected", [
        ("obst-gemuese", OBST_GEMUESE),
        ("brot-gebaeck", BROT_GEBAECK),
        ("milchprodukte-alternativen", MILCHPRODUKTE),
        ("wurst-fleisch-eier-fisch", FLEISCH_FISCH),
        ("tiefkuehlprodukte", TIEFKUEHL),
        ("alkoholfreie-getraenke", GETRAENKE),
        ("alkoholische-getraenke", ALKOHOL),
        ("suesses-salziges", SUESSES_SNACKS),
        ("kaffee-tee-kakao", KAFFEE_TEE),
        ("backen-fruehstueck", FRUEHSTUECK_AUFSTRICHE),
        ("beilagen-essig-oel-gewuerze", GRUNDNAHRUNGSMITTEL),
        ("schnelle-kueche-to-go", FERTIGGERICHTE),
        ("babynahrung", BABY_TIER),
    ])
    def test_spar_category(self, raw, expected):
        assert normalize_category(raw) == expected


class TestExactMatchHofer:
    @pytest.mark.parametrize("raw,expected", [
        ("brot-und-backwaren", BROT_GEBAECK),
        ("fleisch-und-fisch", FLEISCH_FISCH),
        ("getraenke", GETRAENKE),
        ("kuehlung", MILCHPRODUKTE),
        ("suesses-und-salziges", SUESSES_SNACKS),
        ("tiefkuehlung", TIEFKUEHL),
        ("vorratsschrank", GRUNDNAHRUNGSMITTEL),
    ])
    def test_hofer_category(self, raw, expected):
        assert normalize_category(raw) == expected


class TestExactMatchLidl:
    @pytest.mark.parametrize("raw,expected", [
        ("Obst & Gemüse", OBST_GEMUESE),
        ("Frisches Brot & Gebäck", BROT_GEBAECK),
        ("Käse & Molkerei", MILCHPRODUKTE),
        ("Fleisch & Wurst", FLEISCH_FISCH),
        ("Fisch & Meeresfrüchte", FLEISCH_FISCH),
        ("Tiefkühlkost", TIEFKUEHL),
        ("Getränke", GETRAENKE),
        ("Snacks & Süßigkeiten", SUESSES_SNACKS),
        ("Kaffee, Tee & Kakao", KAFFEE_TEE),
        ("Fertiggerichte", FERTIGGERICHTE),
        ("Wein & Spirituosen", ALKOHOL),
        ("Drogerie", DROGERIE_HAUSHALT),
    ])
    def test_lidl_category(self, raw, expected):
        assert normalize_category(raw) == expected


class TestExactMatchPenny:
    @pytest.mark.parametrize("raw,expected", [
        ("Obst", OBST_GEMUESE),
        ("Brot & Gebäck", BROT_GEBAECK),
        ("Milchprodukte", MILCHPRODUKTE),
        ("Fleisch", FLEISCH_FISCH),
        ("Fisch", FLEISCH_FISCH),
        ("Alkoholfreie Getränke", GETRAENKE),
        ("Schokolade", SUESSES_SNACKS),
        ("Kaffee, Tee & Co.", KAFFEE_TEE),
        ("Reis, Teigwaren & Sugo", GRUNDNAHRUNGSMITTEL),
        ("Schnelle Küche", FERTIGGERICHTE),
        ("Honig, Marmelade & Co.", FRUEHSTUECK_AUFSTRICHE),
        ("Bier & Radler", ALKOHOL),
        ("Wein", ALKOHOL),
        ("Haushalt", DROGERIE_HAUSHALT),
        ("Hunde", BABY_TIER),
        ("Katzen", BABY_TIER),
    ])
    def test_penny_category(self, raw, expected):
        assert normalize_category(raw) == expected


class TestExactMatchBilla:
    """Billa has many fine-grained categories. Test representative ones."""

    @pytest.mark.parametrize("raw,expected", [
        ("Kartoffeln", OBST_GEMUESE),
        ("Toastbrot", BROT_GEBAECK),
        ("Fruchtjoghurt", MILCHPRODUKTE),
        ("Butter", MILCHPRODUKTE),
        ("Rindfleisch", FLEISCH_FISCH),
        ("Frischfisch", FLEISCH_FISCH),
        ("Eiscreme", TIEFKUEHL),
        ("Pizza", TIEFKUEHL),
        ("Limonaden", GETRAENKE),
        ("Energydrinks", GETRAENKE),
        ("Tafelschokolade", SUESSES_SNACKS),
        ("Chips", SUESSES_SNACKS),
        ("Ganze Bohne", KAFFEE_TEE),
        ("Kräutertee", KAFFEE_TEE),
        ("Spaghetti", GRUNDNAHRUNGSMITTEL),
        ("Ketchup", GRUNDNAHRUNGSMITTEL),
        ("Internationale Küche", FERTIGGERICHTE),
        ("Müsli", FRUEHSTUECK_AUFSTRICHE),
        ("Honig", FRUEHSTUECK_AUFSTRICHE),
        ("Flaschenbier", ALKOHOL),
        ("Rotwein", ALKOHOL),
        ("Gin", ALKOHOL),
        ("Shampoo & Spülung", DROGERIE_HAUSHALT),
        ("WC Papier", DROGERIE_HAUSHALT),
        ("Windeln", BABY_TIER),
        ("Nassfutter", BABY_TIER),
    ])
    def test_billa_category(self, raw, expected):
        assert normalize_category(raw) == expected


class TestKeywordFallback:
    """Categories not in the exact-match dict should be caught by keywords."""

    @pytest.mark.parametrize("raw,expected", [
        ("Frisches Gemüse Sortiment", OBST_GEMUESE),
        ("Neue Brotsorten", BROT_GEBAECK),
        ("Spezial-Käseplatte", MILCHPRODUKTE),
        ("Grillwurst Sortiment", FLEISCH_FISCH),
        ("Tiefkühl-Neuheiten", TIEFKUEHL),
        ("Saft-Neuheiten", GETRAENKE),
        ("Schoko-Spezialitäten", SUESSES_SNACKS),
        ("Kaffee Spezialitäten", KAFFEE_TEE),
        ("Premium Pasta", GRUNDNAHRUNGSMITTEL),
        ("Asiatisch Fertiggericht", FERTIGGERICHTE),
        ("Bio Müsli Mix", FRUEHSTUECK_AUFSTRICHE),
        ("Craft Bier Auswahl", ALKOHOL),
        ("Haushaltspflege Premium", DROGERIE_HAUSHALT),
        ("Babypflege Organic", BABY_TIER),
    ])
    def test_keyword_match(self, raw, expected):
        assert normalize_category(raw) == expected


class TestEdgeCases:
    def test_none_returns_sonstiges(self):
        assert normalize_category(None) == SONSTIGES

    def test_empty_string_returns_sonstiges(self):
        assert normalize_category("") == SONSTIGES

    def test_unknown_category_returns_sonstiges(self):
        assert normalize_category("Totally Unknown Category XYZ") == SONSTIGES

    def test_result_always_in_normalized_list(self):
        """Every result must be one of the defined normalized categories."""
        test_inputs = [
            None, "", "obst-gemuese", "Fleisch", "Something Random",
            "milchprodukte-alternativen", "Chips & Co.",
        ]
        for raw in test_inputs:
            result = normalize_category(raw)
            assert result in NORMALIZED_CATEGORIES, f"{raw!r} → {result!r}"


class TestNormalizedCategoryInScrapers:
    """Verify scraper parse functions include normalizedCategory."""

    def test_billa_parse_includes_normalized(self):
        from scrapers.billa import _parse_product

        product = {
            "sku": "00-123456",
            "name": "Bio Vollmilch",
            "price": {"regular": {"value": 149}},
            "category": "Milch",
        }
        result = _parse_product(product)
        assert result is not None
        assert "normalizedCategory" in result
        assert result["normalizedCategory"] == MILCHPRODUKTE

    def test_penny_parse_includes_normalized(self):
        from scrapers.penny import _parse_product

        product = {
            "sku": "99-001",
            "name": "Knusprige Chips",
            "price": {"regular": {"value": 199}},
            "category": "Chips & Co.",
        }
        result = _parse_product(product)
        assert result is not None
        assert result["normalizedCategory"] == SUESSES_SNACKS

    def test_lidl_parse_includes_normalized(self):
        from scrapers.lidl import _parse_product

        item = {
            "gridbox": {
                "data": {
                    "fullTitle": "Rindsgulasch",
                    "price": {"price": 5.99},
                    "productId": "12345",
                    "category": "Fleisch & Wurst",
                    "brand": {"name": "Metzgerfrisch"},
                    "image": "https://example.com/img.jpg",
                }
            }
        }
        result = _parse_product(item)
        assert result is not None
        assert result["normalizedCategory"] == FLEISCH_FISCH

    def test_none_category_gets_sonstiges(self):
        from scrapers.billa import _parse_product

        product = {
            "sku": "00-999",
            "name": "Test",
            "price": {"regular": {"value": 100}},
        }
        result = _parse_product(product)
        assert result is not None
        assert result["normalizedCategory"] == SONSTIGES
