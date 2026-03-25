import json
import os
import re
import time
from datetime import date
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "screenshots"

BASE_URL = "https://www.hofer.at/de/sortiment/produktsortiment/{category}.html"
OFFERS_URL = "https://www.hofer.at/de/angebote.html"

CATEGORIES = [
    "brot-und-backwaren",
    "fleisch-und-fisch",
    "getraenke",
    "kuehlung",
    "vorratsschrank",
    #"drogerie",
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
        price_text = price_el.inner_text().strip().replace("€", "").replace(".", "").replace(",", ".").strip()
        try:
            price = float(re.sub(r"[^\d.]", "", price_text))
        except ValueError:
            price = None

    original_price = None
    if original_price_el:
        op_text = original_price_el.inner_text().strip().replace("€", "").replace(".", "").replace(",", ".").strip()
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
            page_obj.wait_for_timeout(1000)
        except Exception:
            break

        after_count = len(page_obj.query_selector_all("div.plp_product[data-productid]"))
        if after_count <= before_count:
            # Give it one more chance
            page_obj.wait_for_timeout(1000)
            after_count = len(page_obj.query_selector_all("div.plp_product[data-productid]"))
            if after_count <= before_count:
                break


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


def _get_offer_date_links(page_obj):
    """Extract date-based offer links from the offers page, filtered to today or earlier."""
    today = date.today()
    links = page_obj.query_selector_all("a[href*='/de/angebote/d.']")
    valid_urls = []
    seen = set()

    for link in links:
        href = link.get_attribute("href") or ""
        # Extract date from URL pattern like /de/angebote/d.23-03-2026.html
        match = re.search(r"/d\.(\d{2})-(\d{2})-(\d{4})\.html", href)
        if not match:
            continue

        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        offer_date = date(year, month, day)

        if offer_date <= today and href not in seen:
            full_url = href if href.startswith("http") else f"https://www.hofer.at{href}"
            valid_urls.append((offer_date, full_url))
            seen.add(href)

    # Sort by date descending (newest first)
    valid_urls.sort(key=lambda x: x[0], reverse=True)
    print(f"  Found {len(valid_urls)} current/past offer dates (skipped future)")
    for d, url in valid_urls:
        print(f"    {d.strftime('%d.%m.%Y')}: {url}")
    return valid_urls


def _scrape_offer_page(browser, offer_date, url):
    """Scrape all products from a single offer date page."""
    context = browser.new_context(user_agent=USER_AGENT)
    page_obj = context.new_page()
    products = []

    try:
        page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_obj.wait_for_selector("div.plp_product[data-productid]", timeout=30000)

        _dismiss_cookie_banner(page_obj)
        _click_show_more(page_obj)

        tiles = page_obj.query_selector_all("div.plp_product[data-productid]")
        date_label = offer_date.strftime("%d.%m.%Y")
        for tile in tiles:
            product = _parse_tile(tile, "angebote")
            product["inPromotion"] = True
            product["promotionText"] = f"ab {date_label}"
            products.append(product)

        print(f"hofer offers {date_label}: {len(products)} products")

    except Exception as e:
        label = offer_date.strftime("%Y%m%d")
        _take_screenshot(page_obj, f"offers_{label}", "failure")
        print(f"Error scraping offers for {offer_date}: {e}")
    finally:
        context.close()

    return products


def _scrape_offers(browser):
    """Scrape all current offer date pages and return a flat list of product dicts."""
    context = browser.new_context(user_agent=USER_AGENT)
    page_obj = context.new_page()
    offer_links = []

    try:
        page_obj.goto(OFFERS_URL, wait_until="domcontentloaded", timeout=30000)
        page_obj.wait_for_timeout(2000)
        _dismiss_cookie_banner(page_obj)
        offer_links = _get_offer_date_links(page_obj)
    except Exception as e:
        print(f"Error loading offers page: {e}")
    finally:
        context.close()

    all_offer_products = []
    for idx, (offer_date, url) in enumerate(offer_links):
        products = _scrape_offer_page(browser, offer_date, url)
        all_offer_products.extend(products)


    return all_offer_products


def scrape_hofer():
    """Scrape all categories and return a flat list of product dicts."""
    all_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for category in CATEGORIES:
                try:
                    products = _scrape_category(browser, category)
                    all_products.extend(products)

                except Exception as e:
                    print(f"Error scraping category '{category}': {e}")

            # Scrape offers (date-based promotion pages)
            print("\nScraping Hofer offers...")
            try:
                offer_products = _scrape_offers(browser)
                all_products.extend(offer_products)
                print(f"hofer offers total: {len(offer_products)} products")
            except Exception as e:
                print(f"Error scraping offers: {e}")
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
    
    with open("hofer.json", "w", encoding="utf-8") as f:
        json.dump(unique_products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique_products)} products to hofer.json")
    
    return unique_products
