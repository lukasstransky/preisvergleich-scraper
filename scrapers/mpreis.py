import json
import os
import re
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "screenshots"

PAGES = [
    ("lebensmittel", "https://www.mpreis.at/shop/c/lebensmittel-50234186"),
    ("getraenke", "https://www.mpreis.at/shop/c/getraenke-13743475"),
    ("aktionen", "https://www.mpreis.at/aktionen/aktuell/alle-produkte-in-aktion"),
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Resource types to block for faster page loading.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


async def _block_unnecessary_resources(route):
    """Abort requests for non-essential resources to speed up page loading."""
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()


def _extract_sku(tile):
    """Extract the numeric SKU from the product tile.

    Sources (tried in order):
      1. CSS class ``c3-item-<digits>``
      2. ``href`` attribute, last segment ``…-<digits>``
    """
    classes = tile.get_attribute("class") or ""
    match = re.search(r"c3-item-(\d+)", classes)
    if match:
        return match.group(1)

    href = tile.get_attribute("href") or ""
    match = re.search(r"-(\d+)$", href.rstrip("/"))
    if match:
        return match.group(1)
    return None


def _parse_price_text(text):
    """Parse an Austrian price string like ``1,99`` or ``12,49`` into a float."""
    if not text:
        return None
    cleaned = text.strip().replace("€", "").replace("\xa0", "").strip()
    cleaned = cleaned.replace(",", ".")
    # Remove any stray non-numeric characters except dot
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_unit_text(text):
    """Parse unit-price text like ``2,00€ /kg`` into (unit_price, unit_label).

    Returns (None, None) when nothing can be extracted.
    """
    if not text:
        return None, None
    # Pattern: "2,00€ /kg" or "14,68€ /kg" or "1,99€ /Stk" or "1,99€ /l"
    match = re.search(r"([\d]+[,.][\d]+)\s*€?\s*/\s*(\S+)", text)
    if match:
        price_str = match.group(1).replace(",", ".")
        unit_raw = match.group(2).strip()
        try:
            price = float(price_str)
        except ValueError:
            return None, None
        return price, unit_raw
    return None, None


def _parse_tile(tile, category):
    """Parse a single ``a.c3-product`` element into a product dict."""
    sku = _extract_sku(tile)

    # Brand / producer
    brand_el = tile.query_selector("span.c3-product__producer")
    brand = brand_el.inner_text().strip() if brand_el else None

    # Product name
    name_el = tile.query_selector("span.c3-product__name")
    name = name_el.inner_text().strip() if name_el else ""

    # Weight / amount
    weight_el = tile.query_selector("div.c3-product__weight-info-text")
    amount = weight_el.inner_text().strip() if weight_el else None

    # Image URL (prefer the non-srcset img src)
    img_el = tile.query_selector("img.c3-image")
    image_url = None
    if img_el:
        src = img_el.get_attribute("src") or ""
        if src and not src.startswith("/assets/noImage"):
            image_url = src if src.startswith("http") else f"https://www.mpreis.at{src}"

    # --- Price extraction ---
    price = None
    original_price = None
    promotion_text = None
    in_promotion = False

    # Try screen-reader text first: "Aktueller Preis 1,00 €, statt 1,79 €"
    sr_el = tile.query_selector("div.sr-only")
    if sr_el:
        sr_text = sr_el.inner_text().strip()
        current_match = re.search(r"Aktueller Preis\s+([\d,]+)\s*€", sr_text)
        original_match = re.search(r"statt\s+([\d,]+)\s*€", sr_text)
        if current_match:
            price = _parse_price_text(current_match.group(1))
        if original_match:
            original_price = _parse_price_text(original_match.group(1))
            in_promotion = True

    # Fallback: extract price from the price div text content
    if price is None:
        price_div = tile.query_selector("div.c3-product__price")
        if price_div:
            # The price is a direct text node like "1,99" or "2,79"
            # We need to get only the direct text, not children text
            price_text = price_div.evaluate(
                """el => {
                    let text = '';
                    for (const node of el.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            text += node.textContent;
                        }
                    }
                    return text;
                }"""
            )
            price = _parse_price_text(price_text)

    # Original (struck-through) price fallback
    if original_price is None:
        strike_el = tile.query_selector("div.c3-product__price-discount-info-strike")
        if strike_el:
            original_price = _parse_price_text(strike_el.inner_text())
            in_promotion = True

    # Discount percentage text (e.g., "-44%")
    discount_el = tile.query_selector("span.c3-product-special__discount-amount")
    if discount_el:
        promotion_text = discount_el.inner_text().strip()
        in_promotion = True

    # Multi-buy promo text (e.g., "Ab 2 Stk. je" + "ab 2" / "billiger")
    if not promotion_text:
        promo_info_el = tile.query_selector("div.c3-product__price-discount-info:not(.c3-product__price-discount-info-strike)")
        if promo_info_el:
            promo_text = promo_info_el.inner_text().strip()
            if promo_text:
                promotion_text = promo_text
                in_promotion = True

    if not promotion_text:
        multibuy_el = tile.query_selector("div.c3-product-special__oneplusone")
        free_el = tile.query_selector("div.c3-product-special__free")
        if multibuy_el and free_el:
            promotion_text = f"{multibuy_el.inner_text().strip()} {free_el.inner_text().strip()}"
            in_promotion = True

    # Unit price (e.g., "1,99€ /Stk", "2,00€ /kg")
    unit_el = tile.query_selector("div.c3-product__unit")
    unit_price, unit_label = _parse_unit_text(unit_el.inner_text().strip() if unit_el else None)

    # For the aktionen page, always mark as in promotion
    if category == "aktionen":
        in_promotion = True

    return {
        "id": f"mpreis_{sku}" if sku else None,
        "name": name,
        "price": price,
        "originalPrice": original_price,
        "promotionText": promotion_text,
        "unitPrice": unit_price,
        "unitLabel": unit_label,
        "category": category,
        "brand": brand,
        "amount": amount,
        "sku": sku,
        "inPromotion": in_promotion,
        "imageUrl": image_url,
        "supermarket": "mpreis",
    }


def _dismiss_cookie_banner(page_obj):
    """Accept cookie consent if the banner appears."""
    try:
        btn = page_obj.query_selector('button:has-text("Akzeptieren")')
        if btn and btn.is_visible():
            btn.click()
            page_obj.wait_for_timeout(1000)
    except Exception:
        pass


def _click_load_more(page_obj, category=""):
    """Click 'Mehr laden' button repeatedly until all products are loaded.

    The button is wrapped in a Vue router ``<a>`` tag, so each click triggers a
    client-side navigation.  We therefore wait for the product selector to re-
    appear after every click and tolerate several consecutive "stale" clicks
    where no new products are added (the SPA can be slow).
    """
    max_clicks = 200
    stale_attempts = 0
    max_stale = 5  # allow several consecutive zero-delta clicks before giving up

    for click_num in range(1, max_clicks + 1):
        btn = page_obj.query_selector("button.c3-load-more__button")
        if not btn:
            break
        try:
            if not btn.is_visible():
                break
        except Exception:
            break

        before_count = len(page_obj.query_selector_all("a.c3-product"))

        try:
            btn.scroll_into_view_if_needed()
            page_obj.wait_for_timeout(300)
            btn.click()
            # Wait for DOM update after Vue router navigation
            page_obj.wait_for_timeout(2500)
            # Re-wait for product tiles (they re-render after navigation)
            try:
                page_obj.wait_for_selector("a.c3-product", timeout=10000)
            except Exception:
                pass
        except Exception:
            break

        after_count = len(page_obj.query_selector_all("a.c3-product"))

        if after_count <= before_count:
            # Wait longer and re-check – the page can be slow
            page_obj.wait_for_timeout(3000)
            after_count = len(page_obj.query_selector_all("a.c3-product"))

        if after_count > before_count:
            stale_attempts = 0
        else:
            stale_attempts += 1
            if stale_attempts >= max_stale:
                break

        if click_num % 10 == 0:
            print(f"  mpreis {category}: loaded {after_count} products ({click_num} pages)...")


def _take_screenshot(page_obj, label, suffix):
    """Save a screenshot to SCREENSHOT_DIR for debugging."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = os.path.join(SCREENSHOT_DIR, f"mpreis_{label}_{suffix}.png")
    try:
        page_obj.screenshot(path=filename, full_page=True)
        print(f"Screenshot saved: {filename}")
    except Exception as e:
        print(f"Failed to save screenshot: {e}")


def _scrape_page(browser, category, url):
    """Scrape all products from a single MPreis page."""
    context = browser.new_context(user_agent=USER_AGENT)
    page_obj = context.new_page()
    products = []

    try:
        page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_obj.wait_for_timeout(3000)

        _dismiss_cookie_banner(page_obj)

        # Wait for product tiles to appear after cookie dismissal
        page_obj.wait_for_selector("a.c3-product", timeout=30000)
        page_obj.wait_for_timeout(2000)

        _click_load_more(page_obj, category)

        tiles = page_obj.query_selector_all("a.c3-product")
        for tile in tiles:
            product = _parse_tile(tile, category)
            if product["price"] is not None:
                products.append(product)

        print(f"mpreis {category}: {len(products)} products")

    except Exception as e:
        _take_screenshot(page_obj, category, "failure")
        print(f"Error scraping mpreis {category}: {e}")
    finally:
        context.close()

    return products


def scrape_mpreis():
    """Scrape all MPreis pages and return a flat list of product dicts."""
    all_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for category, url in PAGES:
                try:
                    products = _scrape_page(browser, category, url)
                    all_products.extend(products)
                except Exception as e:
                    print(f"Error scraping mpreis '{category}': {e}")
        finally:
            browser.close()

    # Deduplicate products that appear on multiple pages (keep first occurrence)
    seen_skus = set()
    unique_products = []
    for product in all_products:
        sku = product["sku"]
        if sku and sku in seen_skus:
            continue
        if sku:
            seen_skus.add(sku)
        unique_products.append(product)

    print(f"mpreis total: {len(unique_products)} products ({len(all_products) - len(unique_products)} duplicates removed)")

    with open("mpreis.json", "w", encoding="utf-8") as f:
        json.dump(unique_products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique_products)} products to mpreis.json")

    return unique_products
