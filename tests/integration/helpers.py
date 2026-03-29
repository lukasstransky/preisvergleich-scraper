"""Helpers: realistic API responses & Playwright mocks for integration tests."""

import re
from unittest.mock import MagicMock, AsyncMock, PropertyMock


# ──────────────────────────────────────────────────────────────────────────────
# Billa / Penny API response factories
# ──────────────────────────────────────────────────────────────────────────────

def make_billa_api_product(sku="00-427631", name="Lindt Goldhase", price_cents=499,
                           crossed=None, per_qty=499, promo_text=None,
                           base_unit="g", category="Schokolade", brand_name="Lindt",
                           in_promo=False, image_url="https://images.example.com/lindt.jpg"):
    """Return a single product dict matching the Billa/Penny REST API shape."""
    return {
        "sku": sku,
        "name": name,
        "price": {
            "regular": {
                "value": price_cents,
                "perStandardizedQuantity": per_qty,
                "promotionText": promo_text,
            },
            "crossed": crossed,
            "baseUnitShort": base_unit,
        },
        "category": category,
        "brand": {"name": brand_name} if brand_name else None,
        "inPromotion": in_promo,
        "images": [image_url] if image_url else None,
    }


def make_billa_api_response(products, offset=0):
    """Wrap products in the paginated API response envelope."""
    return {
        "results": products,
        "offset": offset,
        "count": len(products),
        "total": offset + len(products),
    }


SAMPLE_BILLA_PRODUCTS = [
    make_billa_api_product("00-100001", "Bio Vollmilch", 139, base_unit="l",
                           category="Milch", brand_name="Ja! Natürlich"),
    make_billa_api_product("00-100002", "Butter", 299, crossed=359,
                           per_qty=299, base_unit="kg", category="Milch",
                           brand_name="Ja! Natürlich", in_promo=True),
    make_billa_api_product("00-100003", "Vollkornbrot", 249,
                           base_unit="kg", category="Brot", brand_name=None),
]


def make_penny_offers_html(tab_slugs):
    """Return minimal HTML for the Penny /angebote page with given tab slugs.

    tab_slugs: list of (day, month) tuples, e.g. [(19, 3), (26, 3)].
    """
    links = "\n".join(
        f'<a href="/angebote?tab=angebote-ab-{d:02d}-{m:02d}">Ab {d}.{m}.</a>'
        for d, m in tab_slugs
    )
    return f"<html><body>{links}</body></html>"


# ──────────────────────────────────────────────────────────────────────────────
# Spar Playwright mock helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_async_element(text="", attrs=None):
    """Create an async mock element with inner_text() and get_attribute()."""
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    attrs = attrs or {}
    el.get_attribute = AsyncMock(side_effect=lambda k: attrs.get(k))
    return el


def make_spar_tile(sku="2020005521308", brand="SPAR PREMIUM", name="Bio Apfel",
                   amount="500 G", price_text="2,99", unit_text="Per 1 kg 5,98",
                   image_url="https://cdn1.interspar.at/at/2020005521308/HB_500px.jpg",
                   link_href="/produkte/spar-premium-bio-apfel-2020005521308/",
                   badge_urls=None):
    """Return an AsyncMock mimicking an ``article.product-tile`` Playwright element.

    *badge_urls*: optional list of badge image URLs (e.g. Bio, AMA icons)
    that appear before the product image in the DOM.
    """
    tile = AsyncMock()

    # Build the list of <img> elements the tile contains.
    # Badge images come first (matching the real DOM order).
    img_elements = []
    for badge_url in (badge_urls or []):
        img_elements.append(_make_async_element(attrs={
            "src": badge_url,
            "class": "tile-basic__badge--top",
            "data-src": None,
            "srcset": "",
        }))
    # The actual product image
    product_img_el = _make_async_element(attrs={
        "src": image_url,
        "class": "tile-basic__image tile-basic__image--product",
        "data-src": None,
        "srcset": "",
    })
    img_elements.append(product_img_el)

    # query_selector returns child elements
    tile.query_selector = AsyncMock(side_effect=lambda sel: {
        "div.product-tile__name1": _make_async_element(brand),
        "div.product-tile__name2": _make_async_element(name),
        "div.product-tile__name3": _make_async_element(amount),
        "span.product-price__price": _make_async_element(price_text),
        'span[data-tosca="product-price-comparison-price"]': _make_async_element(unit_text),
        "img.tile-basic__image--product": product_img_el,
        'a[href*="/produktwelt/"]': _make_async_element(attrs={"href": link_href}),
        "a[href]": _make_async_element(attrs={"href": link_href}),
    }.get(sel))

    # query_selector_all for "img" returns all images (badges + product)
    tile.query_selector_all = AsyncMock(side_effect=lambda sel: img_elements if sel == "img" else [])

    return tile


SAMPLE_SPAR_TILES = [
    make_spar_tile("2020005521308", "SPAR PREMIUM", "Salattomate Rispe", "500 G",
                   "2,99", "Per 1 kg 5,98",
                   "https://cdn1.interspar.at/at/2020005521308/HB_500px.jpg",
                   "/produkte/spar-premium-salattomate-2020005521308/"),
    make_spar_tile("2020005521309", "SPAR", "Bananen", "1 kg",
                   "1,49", "Per 1 kg 1,49",
                   "https://cdn1.interspar.at/at/2020005521309/HB_500px.jpg",
                   "/produkte/spar-bananen-2020005521309/"),
    make_spar_tile("2020005521310", "SPAR NATUR*PUR", "Bio Karotten", "1 kg",
                   "1,99", "Per 1 kg 1,99",
                   "https://cdn1.interspar.at/at/2020005521310/HB_500px.jpg",
                   "/produkte/spar-naturpur-bio-karotten-2020005521310/"),
]


def make_spar_mock_page(tiles, pagination_text="1 von 1"):
    """Return an async mock Playwright page suitable for spar scraping."""
    page = AsyncMock()

    # Navigation & waiting
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    # Cookie banner — dismiss silently
    cookie_btn = AsyncMock()
    cookie_btn.wait_for = AsyncMock()
    cookie_btn.click = AsyncMock()
    locator = MagicMock()
    locator.first = cookie_btn
    page.locator = MagicMock(return_value=locator)

    # Pagination text
    pagination_el = AsyncMock()
    pagination_el.inner_text = AsyncMock(return_value=pagination_text)

    page.query_selector = AsyncMock(side_effect=lambda sel: {
        "div.pagination__text": pagination_el,
    }.get(sel))

    page.query_selector_all = AsyncMock(return_value=tiles)
    page.inner_text = AsyncMock(return_value="Showing products")

    return page


def make_spar_mock_browser(pages):
    """Return a mock browser that creates contexts yielding the given pages."""
    browser = AsyncMock()
    ctx_mocks = []
    for pg in pages:
        ctx = AsyncMock()
        ctx.new_page = AsyncMock(return_value=pg)
        ctx.close = AsyncMock()
        ctx_mocks.append(ctx)
    browser.new_context = AsyncMock(side_effect=ctx_mocks)
    browser.close = AsyncMock()
    return browser


# ──────────────────────────────────────────────────────────────────────────────
# Hofer Playwright mock helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_sync_element(text="", attrs=None):
    """Create a sync MagicMock element with inner_text() and get_attribute()."""
    el = MagicMock()
    el.inner_text = MagicMock(return_value=text)
    attrs = attrs or {}
    el.get_attribute = MagicMock(side_effect=lambda k: attrs.get(k))
    el.is_visible = MagicMock(return_value=True)
    return el


def make_hofer_tile(sku="000000000000101899", full_name="AMERICAN Sandwich",
                    price_text="1,29", original_price_text=None,
                    unit_text="per Packung (1 per Kilogramm = € 1,72 )",
                    image_url="https://s7g10.scene7.com/is/image/aldi/202501280009"):
    """Return a MagicMock mimicking a ``div.plp_product[data-productid]`` element."""
    tile = MagicMock()
    tile.get_attribute = MagicMock(side_effect=lambda k: {
        "data-productid": sku,
    }.get(k))

    name_el = _make_sync_element(full_name)
    price_el = _make_sync_element(price_text)
    original_el = _make_sync_element(original_price_text) if original_price_text else None
    unit_el = _make_sync_element(unit_text) if unit_text else None
    img_el = _make_sync_element(attrs={"data-src": image_url, "src": None})

    tile.query_selector = MagicMock(side_effect=lambda sel: {
        "h2.product-title": name_el,
        "span.at-product-price_lbl": price_el,
        ".price_before del": original_el,
        "span.additional-product-info": unit_el,
        "img.at-product-images_img": img_el,
    }.get(sel))

    return tile


SAMPLE_HOFER_TILES = [
    make_hofer_tile("000000000000101899", "AMERICAN Sandwich", "1,29", "1,89",
                    "per Packung (1 per Kilogramm = € 1,72 )"),
    make_hofer_tile("000000000000101900", "BACKBOX Butter-Briocheknopf", "0,99",
                    unit_text="per Stück"),
    make_hofer_tile("000000000000101901", "Vollkornbrot", "2,49",
                    unit_text="per Packung (1 per Kilogramm = € 4,98 )"),
]


def make_hofer_mock_page(tiles, offer_links=None):
    """Return a sync MagicMock Playwright page suitable for hofer scraping.

    ``offer_links`` is a list of (href, visible) tuples for the offers page.
    If None, the page behaves as a category page.
    """
    page = MagicMock()

    page.goto = MagicMock()
    page.wait_for_selector = MagicMock()
    page.wait_for_timeout = MagicMock()

    # Cookie banner — visible and clickable
    cookie_btn = MagicMock()
    cookie_btn.is_visible = MagicMock(return_value=True)
    cookie_btn.click = MagicMock()

    def qs(sel):
        if sel == "button#onetrust-accept-btn-handler":
            return cookie_btn
        if sel == "button#showMore":
            return None  # no "load more" button
        return None

    page.query_selector = MagicMock(side_effect=qs)
    page.query_selector_all = MagicMock(return_value=tiles)
    page.screenshot = MagicMock()

    if offer_links is not None:
        # For the offers index page: return link elements
        link_els = []
        for href in offer_links:
            link_el = MagicMock()
            link_el.get_attribute = MagicMock(return_value=href)
            link_els.append(link_el)

        def qsa(sel):
            if "angebote/d." in sel:
                return link_els
            if "plp_product" in sel:
                return tiles
            return []

        page.query_selector_all = MagicMock(side_effect=qsa)

    return page


def make_hofer_mock_browser(pages):
    """Return a sync mock browser that creates contexts yielding the given pages."""
    browser = MagicMock()
    ctx_mocks = []
    for pg in pages:
        ctx = MagicMock()
        ctx.new_page = MagicMock(return_value=pg)
        ctx.close = MagicMock()
        ctx_mocks.append(ctx)
    browser.new_context = MagicMock(side_effect=ctx_mocks)
    browser.close = MagicMock()
    return browser


# ──────────────────────────────────────────────────────────────────────────────
# Realistic product dicts for Firebase pipeline tests
# ──────────────────────────────────────────────────────────────────────────────

def make_product(supermarket="billa", sku="00-100001", name="Bio Milch",
                 price=1.39, original_price=None, promo_text=None,
                 unit_price=1.39, unit_label="l", category="Milch",
                 brand="Ja! Natürlich", in_promo=False,
                 image_url="https://example.com/image.jpg"):
    """Return a canonical product dict."""
    return {
        "id": f"{supermarket}_{sku}",
        "name": name,
        "price": price,
        "originalPrice": original_price,
        "promotionText": promo_text,
        "unitPrice": unit_price,
        "unitLabel": unit_label,
        "category": category,
        "brand": brand,
        "sku": sku,
        "inPromotion": in_promo,
        "imageUrl": image_url,
        "supermarket": supermarket,
    }
