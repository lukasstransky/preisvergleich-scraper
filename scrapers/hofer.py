import os
import re
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "screenshots"

BASE_URL = "https://www.hofer.at/de/sortiment/produktsortiment/{category}.html"

CATEGORIES = [
    "brot-und-backwaren",
    "fleisch-und-fisch",
    "getraenke",
    "kuehlung",
    "vorratsschrank",
    "drogerie",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _extract_brand(name):
    """Extract brand from product name by taking leading fully-uppercase words.

    Examples:
        'BACKBOX Butter-Briocheknopf'       → ('BACKBOX', 'Butter-Briocheknopf')
        'ZURÜCK ZUM URSPRUNG BIO-Kornspitz' → ('ZURÜCK ZUM URSPRUNG', 'BIO-Kornspitz')
        'DR. OETKER Backdekor'              → ('DR. OETKER', 'Backdekor')
        'Börekstange Spinat-Käse'           → (None, 'Börekstange Spinat-Käse')
    """
    if not name:
        return None, name
    words = name.split()
    brand_words = []
    for word in words:
        alpha_chars = [c for c in word if c.isalpha()]
        if alpha_chars and all(c.isupper() for c in alpha_chars):
            brand_words.append(word)
        else:
            break
    if brand_words:
        brand = " ".join(brand_words)
        product_name = " ".join(words[len(brand_words):])
        # Handle doubled brand prefix (e.g. "LACURA LACURA Sonnencreme")
        if product_name.startswith(brand):
            product_name = product_name[len(brand):].strip()
            # Also strip trailing comma or separator left over
            product_name = product_name.lstrip(",").strip()
        if product_name:
            return brand, product_name
    return None, name


def _parse_unit_info(text):
    """Parse unit info text into (unit_price, unit_label, amount).

    Input examples:
        'per Packung (1 per Kilogramm = € 1,72 )'
        'per Stück'
    """
    if not text:
        return None, None, None

    # Extract selling unit like "per Packung", "per Stück"
    amount_match = re.match(r"(per\s+\S+)", text)
    amount = amount_match.group(1).strip() if amount_match else None

    # Extract unit price like "(1 per Kilogramm = € 1,72)"
    unit_map = {
        "Kilogramm": "kg",
        "Liter": "l",
        "Stück": "Stk",
        "100ml": "100ml",
        "100g": "100g",
    }
    price_match = re.search(r"per\s+([\wäöüÄÖÜ]+)\s*=\s*€\s*([\d,.]+)", text)
    if price_match:
        unit_raw = price_match.group(1)
        price_str = price_match.group(2).replace(",", ".")
        unit_label = unit_map.get(unit_raw, unit_raw)
        try:
            unit_price = float(price_str)
        except ValueError:
            return None, None, amount
        return unit_price, unit_label, amount

    return None, None, amount


def _parse_tile(tile, category):
    """Parse a single product tile element into a product dict."""
    sku = tile.get_attribute("data-productid")

    name_el = tile.query_selector("h2.product-title")
    price_el = tile.query_selector("span.at-product-price_lbl")
    original_price_el = tile.query_selector(".price_before del")
    unit_el = tile.query_selector("span.additional-product-info")
    img_el = tile.query_selector("img.at-product-images_img")

    full_name = name_el.inner_text().strip() if name_el else ""
    brand, name = _extract_brand(full_name)

    price = None
    if price_el:
        price_text = price_el.inner_text().strip().replace("€", "").replace(",", ".").strip()
        try:
            price = float(re.sub(r"[^\d.]", "", price_text))
        except ValueError:
            price = None

    original_price = None
    if original_price_el:
        op_text = original_price_el.inner_text().strip().replace("€", "").replace(",", ".").strip()
        try:
            original_price = float(re.sub(r"[^\d.]", "", op_text))
        except ValueError:
            original_price = None

    unit_text = unit_el.inner_text().strip() if unit_el else None
    unit_price, unit_label, amount = _parse_unit_info(unit_text)

    image_url = None
    if img_el:
        image_url = img_el.get_attribute("data-src") or img_el.get_attribute("src")

    in_promotion = original_price is not None

    return {
        "id": f"hofer_{sku}" if sku else None,
        "name": name if brand else full_name,
        "price": price,
        "originalPrice": original_price,
        "promotionText": None,
        "unitPrice": unit_price,
        "unitLabel": unit_label,
        "category": category,
        "brand": brand,
        "amount": amount,
        "sku": sku,
        "inPromotion": in_promotion,
        "imageUrl": image_url,
        "supermarket": "hofer",
    }


def _dismiss_cookie_banner(page_obj):
    """Accept cookie consent if the banner appears."""
    try:
        btn = page_obj.query_selector("button#onetrust-accept-btn-handler")
        if btn and btn.is_visible():
            btn.click()
            page_obj.wait_for_timeout(1000)
    except Exception:
        pass


def _click_show_more(page_obj):
    """Click 'Mehr anzeigen' button repeatedly until all products are loaded."""
    max_clicks = 50
    for _ in range(max_clicks):
        btn = page_obj.query_selector("button#showMore")
        if not btn or not btn.is_visible():
            break

        before_count = len(page_obj.query_selector_all("div.plp_product[data-productid]"))

        try:
            btn.scroll_into_view_if_needed()
            btn.click()
            page_obj.wait_for_timeout(2000)
        except Exception:
            break

        after_count = len(page_obj.query_selector_all("div.plp_product[data-productid]"))
        if after_count <= before_count:
            # Give it one more chance
            page_obj.wait_for_timeout(2000)
            after_count = len(page_obj.query_selector_all("div.plp_product[data-productid]"))
            if after_count <= before_count:
                break

        print(f"  Loaded more products: {after_count} total")


def _take_screenshot(page_obj, category, label):
    """Save a screenshot to SCREENSHOT_DIR for debugging CI failures."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = os.path.join(SCREENSHOT_DIR, f"hofer_{category}_{label}.png")
    try:
        page_obj.screenshot(path=filename, full_page=True)
        print(f"Screenshot saved: {filename}")
    except Exception as e:
        print(f"Failed to save screenshot: {e}")


def _scrape_category(browser, category):
    """Scrape all products for a single category."""
    context = browser.new_context(user_agent=USER_AGENT)
    page_obj = context.new_page()
    products = []

    try:
        url = BASE_URL.format(category=category)
        page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_obj.wait_for_selector("div.plp_product[data-productid]", timeout=30000)

        _dismiss_cookie_banner(page_obj)
        _click_show_more(page_obj)

        tiles = page_obj.query_selector_all("div.plp_product[data-productid]")
        for tile in tiles:
            product = _parse_tile(tile, category)
            products.append(product)

        print(f"hofer {category}: {len(products)} products")

    except Exception:
        _take_screenshot(page_obj, category, "failure")
        raise
    finally:
        context.close()

    return products


def scrape_hofer():
    """Scrape all categories and return a flat list of product dicts."""
    all_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for idx, category in enumerate(CATEGORIES):
                try:
                    products = _scrape_category(browser, category)
                    all_products.extend(products)

                    if idx < len(CATEGORIES) - 1:
                        print("Waiting 3s before next category...")
                        time.sleep(3)
                except Exception as e:
                    print(f"Error scraping category '{category}': {e}")
        finally:
            browser.close()

    # Deduplicate products that appear in multiple categories (keep first)
    seen_skus = set()
    unique_products = []
    for product in all_products:
        sku = product["sku"]
        if sku and sku in seen_skus:
            continue
        if sku:
            seen_skus.add(sku)
        unique_products.append(product)

    print(f"hofer total: {len(unique_products)} products ({len(all_products) - len(unique_products)} duplicates removed)")
    return unique_products
