import pytest

from scrapers.mpreis import _extract_sku, _parse_price_text, _parse_unit_text, _parse_tile


# ---------------------------------------------------------------------------
# Helpers – lightweight mock for Playwright element handles
# ---------------------------------------------------------------------------

class FakeElement:
    """Minimal mock of a Playwright ElementHandle for unit-testing _parse_tile."""

    def __init__(self, attrs=None, children=None, text="", js_results=None):
        self._attrs = attrs or {}
        self._children = children or {}  # selector -> FakeElement
        self._text = text
        self._js_results = js_results or {}

    def get_attribute(self, name):
        return self._attrs.get(name)

    def query_selector(self, selector):
        return self._children.get(selector)

    def inner_text(self):
        return self._text

    def evaluate(self, js_expr):
        # Return pre-configured results for specific JS expressions
        for key, value in self._js_results.items():
            if key in js_expr:
                return value
        return self._text


# ---------------------------------------------------------------------------
# _extract_sku
# ---------------------------------------------------------------------------

class TestExtractSku:
    def test_from_class(self):
        el = FakeElement(attrs={"class": "c3-product c3-product-grid__item c3-item-541601"})
        assert _extract_sku(el) == "541601"

    def test_from_href(self):
        el = FakeElement(attrs={"class": "c3-product", "href": "/shop/p/m-bio-bio-gurken-541601"})
        assert _extract_sku(el) == "541601"

    def test_class_preferred_over_href(self):
        el = FakeElement(attrs={
            "class": "c3-product c3-item-111111",
            "href": "/shop/p/something-222222",
        })
        assert _extract_sku(el) == "111111"

    def test_none_when_missing(self):
        el = FakeElement(attrs={"class": "c3-product"})
        assert _extract_sku(el) is None

    def test_none_when_no_attrs(self):
        el = FakeElement()
        assert _extract_sku(el) is None


# ---------------------------------------------------------------------------
# _parse_price_text
# ---------------------------------------------------------------------------

class TestParsePriceText:
    def test_simple(self):
        assert _parse_price_text("1,99") == 1.99

    def test_with_euro_sign(self):
        assert _parse_price_text("1,99 €") == 1.99

    def test_large_price(self):
        assert _parse_price_text("12,49") == 12.49

    def test_integer_like(self):
        assert _parse_price_text("1,00") == 1.0

    def test_none(self):
        assert _parse_price_text(None) is None

    def test_empty(self):
        assert _parse_price_text("") is None

    def test_spaces(self):
        assert _parse_price_text("  2,79  ") == 2.79

    def test_garbage(self):
        assert _parse_price_text("abc") is None


# ---------------------------------------------------------------------------
# _parse_unit_text
# ---------------------------------------------------------------------------

class TestParseUnitText:
    def test_per_kg(self):
        price, label = _parse_unit_text("2,00€ /kg")
        assert price == 2.0
        assert label == "kg"

    def test_per_stk(self):
        price, label = _parse_unit_text("1,99€ /Stk")
        assert price == 1.99
        assert label == "Stk"

    def test_per_liter(self):
        price, label = _parse_unit_text("1,99€ /l")
        assert price == 1.99
        assert label == "l"

    def test_large_unit_price(self):
        price, label = _parse_unit_text("14,68€ /kg")
        assert price == 14.68
        assert label == "kg"

    def test_none_input(self):
        price, label = _parse_unit_text(None)
        assert price is None
        assert label is None

    def test_empty_string(self):
        price, label = _parse_unit_text("")
        assert price is None
        assert label is None

    def test_no_match(self):
        price, label = _parse_unit_text("random text")
        assert price is None
        assert label is None


# ---------------------------------------------------------------------------
# _parse_tile – non-promotional product
# ---------------------------------------------------------------------------

class TestParseTileNoPromotion:
    def _make_tile(self):
        """Build a FakeElement tree mimicking a non-promotional product tile."""
        return FakeElement(
            attrs={
                "class": "c3-product c3-product-grid__item c3-item-541601",
                "href": "/shop/p/m-bio-bio-gurken-541601",
            },
            children={
                "span.c3-product__producer": FakeElement(text="M-BIO"),
                "span.c3-product__name": FakeElement(text="BIO Gurken"),
                "div.c3-product__weight-info-text": FakeElement(text="300g"),
                "img.c3-image": FakeElement(attrs={
                    "src": "https://res.cloudinary.com/dit8huoga/image/upload/mpreis/products/manual/manual_541601.jpg",
                }),
                "div.sr-only": None,
                "div.c3-product__price": FakeElement(
                    text="1,99",
                    js_results={"childNodes": "1,99"},
                ),
                "div.c3-product__price-discount-info-strike": None,
                "span.c3-product-special__discount-amount": None,
                "div.c3-product__price-discount-info:not(.c3-product__price-discount-info-strike)": None,
                "div.c3-product-special__oneplusone": None,
                "div.c3-product-special__free": None,
                "div.c3-product__unit": FakeElement(text="1,99€ /Stk"),
            },
        )

    def test_basic_fields(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["id"] == "mpreis_541601"
        assert result["name"] == "BIO Gurken"
        assert result["brand"] == "M-BIO"
        assert result["sku"] == "541601"
        assert result["supermarket"] == "mpreis"
        assert result["category"] == "lebensmittel"

    def test_price(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["price"] == 1.99
        assert result["originalPrice"] is None
        assert result["inPromotion"] is False

    def test_unit_price(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["unitPrice"] == 1.99
        assert result["unitLabel"] == "Stk"

    def test_image(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["imageUrl"] == "https://res.cloudinary.com/dit8huoga/image/upload/mpreis/products/manual/manual_541601.jpg"

    def test_amount(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["amount"] == "300g"


# ---------------------------------------------------------------------------
# _parse_tile – promotional product (with discount)
# ---------------------------------------------------------------------------

class TestParseTileWithPromotion:
    def _make_tile(self):
        """Build a FakeElement tree mimicking a product with a percentage discount."""
        return FakeElement(
            attrs={
                "class": "c3-product c3-product-grid__item c3-item-500201",
                "href": "/shop/p/m-bio-bio-zitronen-500201",
            },
            children={
                "span.c3-product__producer": FakeElement(text="M-BIO"),
                "span.c3-product__name": FakeElement(text="BIO Zitronen"),
                "div.c3-product__weight-info-text": FakeElement(text="500g"),
                "img.c3-image": FakeElement(attrs={
                    "src": "https://res.cloudinary.com/dit8huoga/image/upload/mpreis/products/manual/manual_500201.jpg",
                }),
                "div.sr-only": FakeElement(text="Aktueller Preis 1,00 €, statt 1,79 €"),
                "div.c3-product__price": FakeElement(text="1,00"),
                "div.c3-product__price-discount-info-strike": FakeElement(text="1,79"),
                "span.c3-product-special__discount-amount": FakeElement(text="-44%"),
                "div.c3-product__price-discount-info:not(.c3-product__price-discount-info-strike)": None,
                "div.c3-product-special__oneplusone": None,
                "div.c3-product-special__free": None,
                "div.c3-product__unit": FakeElement(text="2,00€ /kg"),
            },
        )

    def test_prices(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["price"] == 1.0
        assert result["originalPrice"] == 1.79
        assert result["inPromotion"] is True

    def test_promotion_text(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["promotionText"] == "-44%"

    def test_unit_price(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["unitPrice"] == 2.0
        assert result["unitLabel"] == "kg"


# ---------------------------------------------------------------------------
# _parse_tile – multi-buy promotion
# ---------------------------------------------------------------------------

class TestParseTileMultiBuy:
    def _make_tile(self):
        """Build a FakeElement tree mimicking a multi-buy promotion."""
        return FakeElement(
            attrs={
                "class": "c3-product c3-product-grid__item c3-item-108109",
                "href": "/shop/p/m-bio-kokos-drink-108109",
            },
            children={
                "span.c3-product__producer": FakeElement(text="M-BIO"),
                "span.c3-product__name": FakeElement(text="Kokos Drink ungesüßt"),
                "div.c3-product__weight-info-text": FakeElement(text="1000ml"),
                "img.c3-image": FakeElement(attrs={"src": "/assets/noImage_detail-Dcwmob_G.webp"}),
                "div.sr-only": FakeElement(text="Aktueller Preis 1,99 €, statt 2,49 €"),
                "div.c3-product__price": FakeElement(text="1,99"),
                "div.c3-product__price-discount-info-strike": None,
                "span.c3-product-special__discount-amount": None,
                "div.c3-product__price-discount-info:not(.c3-product__price-discount-info-strike)": FakeElement(text="Ab 2 Stk. je"),
                "div.c3-product-special__oneplusone": FakeElement(text="ab 2"),
                "div.c3-product-special__free": FakeElement(text="billiger"),
                "div.c3-product__unit": FakeElement(text="1,99€ /l"),
            },
        )

    def test_prices(self):
        result = _parse_tile(self._make_tile(), "aktionen")
        assert result["price"] == 1.99
        assert result["originalPrice"] == 2.49
        assert result["inPromotion"] is True

    def test_promotion_text(self):
        result = _parse_tile(self._make_tile(), "aktionen")
        assert result["promotionText"] == "Ab 2 Stk. je"

    def test_no_image_placeholder(self):
        result = _parse_tile(self._make_tile(), "aktionen")
        assert result["imageUrl"] is None

    def test_aktionen_always_promotional(self):
        result = _parse_tile(self._make_tile(), "aktionen")
        assert result["inPromotion"] is True


# ---------------------------------------------------------------------------
# _parse_tile – minimal product (missing optional fields)
# ---------------------------------------------------------------------------

class TestParseTileMinimal:
    def _make_tile(self):
        return FakeElement(
            attrs={"class": "c3-product c3-item-999999"},
            children={
                "span.c3-product__producer": None,
                "span.c3-product__name": FakeElement(text="Einfaches Produkt"),
                "div.c3-product__weight-info-text": None,
                "img.c3-image": None,
                "div.sr-only": None,
                "div.c3-product__price": FakeElement(
                    text="3,49",
                    js_results={"childNodes": "3,49"},
                ),
                "div.c3-product__price-discount-info-strike": None,
                "span.c3-product-special__discount-amount": None,
                "div.c3-product__price-discount-info:not(.c3-product__price-discount-info-strike)": None,
                "div.c3-product-special__oneplusone": None,
                "div.c3-product-special__free": None,
                "div.c3-product__unit": None,
            },
        )

    def test_basic_fields(self):
        result = _parse_tile(self._make_tile(), "lebensmittel")
        assert result["id"] == "mpreis_999999"
        assert result["name"] == "Einfaches Produkt"
        assert result["price"] == 3.49
        assert result["brand"] is None
        assert result["amount"] is None
        assert result["imageUrl"] is None
        assert result["unitPrice"] is None
        assert result["unitLabel"] is None
        assert result["originalPrice"] is None
        assert result["inPromotion"] is False
        assert result["promotionText"] is None
        assert result["supermarket"] == "mpreis"
