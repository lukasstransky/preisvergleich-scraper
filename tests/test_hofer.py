import pytest

from scrapers.hofer import _extract_brand, _parse_unit_info


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
