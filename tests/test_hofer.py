from unittest.mock import MagicMock

import pytest

from scrapers.hofer import _extract_brand, _parse_unit_info, _parse_tiefpreis_product


def _make_tiefpreis_container(text, image_url="https://img.example.com/x.jpg"):
    """Build a fake Playwright element for a Tiefpreis-Aktionen tile."""
    container = MagicMock()
    container.inner_text.return_value = text

    img = MagicMock()
    img.get_attribute.side_effect = lambda a: image_url if a in ("data-src", "src") else None

    def _query(selector):
        if selector == "img":
            return img
        return None  # no explicit heading → name falls back to first text line

    container.query_selector.side_effect = _query
    return container


# ---------------------------------------------------------------------------
# _extract_brand
# ---------------------------------------------------------------------------

class TestExtractBrand:
    def test_single_uppercase_brand(self):
        brand, name = _extract_brand("BACKBOX Butter-Briocheknopf")
        assert brand == "BACKBOX"
        assert name == "Butter-Briocheknopf"

    def test_multi_word_brand(self):
        brand, name = _extract_brand("ZURÜCK ZUM URSPRUNG BIO-Kornspitz")
        assert brand == "ZURÜCK ZUM URSPRUNG"
        assert name == "BIO-Kornspitz"

    def test_brand_with_dot(self):
        brand, name = _extract_brand("DR. OETKER Backdekor")
        assert brand == "DR. OETKER"
        assert name == "Backdekor"

    def test_no_brand(self):
        brand, name = _extract_brand("Börekstange Spinat-Käse")
        assert brand is None
        assert name == "Börekstange Spinat-Käse"

    def test_empty_string(self):
        brand, name = _extract_brand("")
        assert brand is None
        assert name == ""

    def test_none_input(self):
        brand, name = _extract_brand(None)
        assert brand is None
        assert name is None

    def test_doubled_brand_prefix(self):
        # Both LACURA words are uppercase → brand captures both,
        # then the doubled-prefix logic strips the repeat from the product name.
        brand, name = _extract_brand("LACURA LACURA Sonnencreme")
        assert brand == "LACURA LACURA"
        assert name == "Sonnencreme"

    def test_all_uppercase_name_becomes_brand_with_no_product(self):
        brand, name = _extract_brand("ONLY UPPERCASE")
        # All words are uppercase, but no remaining product name → brand is None
        assert brand is None
        assert name == "ONLY UPPERCASE"

    def test_single_word_uppercase(self):
        brand, name = _extract_brand("MILKA")
        # Single uppercase word with nothing after → brand is None
        assert brand is None
        assert name == "MILKA"

    def test_brand_with_number_in_word(self):
        brand, name = _extract_brand("S-BUDGET Apfelsaft")
        assert brand == "S-BUDGET"
        assert name == "Apfelsaft"


# ---------------------------------------------------------------------------
# _parse_unit_info
# ---------------------------------------------------------------------------

class TestParseUnitInfo:
    def test_full_info(self):
        text = "per Packung (1 per Kilogramm = € 1,72 )"
        unit_price, unit_label, amount = _parse_unit_info(text)
        assert unit_price == 1.72
        assert unit_label == "kg"
        assert amount == "per Packung"

    def test_per_stueck_only(self):
        unit_price, unit_label, amount = _parse_unit_info("per Stück")
        assert unit_price is None
        assert unit_label is None
        assert amount == "per Stück"

    def test_none_input(self):
        unit_price, unit_label, amount = _parse_unit_info(None)
        assert unit_price is None
        assert unit_label is None
        assert amount is None

    def test_empty_string(self):
        unit_price, unit_label, amount = _parse_unit_info("")
        assert unit_price is None
        assert unit_label is None
        assert amount is None

    def test_liter_unit(self):
        text = "per Flasche (1 per Liter = € 2,50 )"
        unit_price, unit_label, amount = _parse_unit_info(text)
        assert unit_price == 2.50
        assert unit_label == "l"
        assert amount == "per Flasche"

    def test_unknown_unit_passed_through(self):
        text = "per Dose (1 per Meter = € 3,00 )"
        unit_price, unit_label, amount = _parse_unit_info(text)
        assert unit_price == 3.00
        assert unit_label == "Meter"
        assert amount == "per Dose"


# ---------------------------------------------------------------------------
# _parse_tiefpreis_product — id generation (these tiles have no SKU)
# ---------------------------------------------------------------------------

class TestParseTiefpreisProduct:
    def test_gets_stable_hash_id(self):
        text = "SPAK Bio Apfel\n€ 2,49\nper Netz"
        product = _parse_tiefpreis_product(_make_tiefpreis_container(text))
        assert product is not None
        # Must have a non-None id or the Firestore sync skips it entirely.
        assert product["id"] is not None
        assert product["id"].startswith("hofer_hash_")

    def test_id_is_stable_across_runs(self):
        text = "SPAK Bio Apfel\n€ 2,49\nper Netz"
        a = _parse_tiefpreis_product(_make_tiefpreis_container(text))
        b = _parse_tiefpreis_product(_make_tiefpreis_container(text))
        assert a["id"] == b["id"]

    def test_id_unchanged_when_only_price_changes(self):
        """A price change must keep the same id so history/diff stay intact."""
        cheap = _parse_tiefpreis_product(_make_tiefpreis_container("SPAK Bio Apfel\n€ 2,49\nper Netz"))
        pricey = _parse_tiefpreis_product(_make_tiefpreis_container("SPAK Bio Apfel\n€ 3,99\nper Netz"))
        assert cheap["id"] == pricey["id"]
        assert cheap["price"] != pricey["price"]

    def test_different_products_get_different_ids(self):
        a = _parse_tiefpreis_product(_make_tiefpreis_container("SPAK Bio Apfel\n€ 2,49\nper Netz"))
        b = _parse_tiefpreis_product(_make_tiefpreis_container("SPAK Bio Birne\n€ 2,49\nper Netz"))
        assert a["id"] != b["id"]
