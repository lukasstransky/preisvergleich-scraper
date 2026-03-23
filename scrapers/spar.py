import os
import re
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "screenshots"

BASE_URL = "https://www.spar.at/produktwelt/{category}?page={page}"

CATEGORIES = [
    "obst-gemuese",
    "brot-gebaeck",
    "milchprodukte-alternativen",
    "tiefkuehlprodukte",
    "wurst-fleisch-eier-fisch",
    "beilagen-essig-oel-gewuerze",
    "backen-fruehstueck",
    "suesses-salziges",
    "schnelle-kueche-to-go",
    "babynahrung",
    "alkoholfreie-getraenke",
    "kaffee-tee-kakao",
    "alkoholische-getraenke",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _extract_sku(image_url):
    """Extract SKU from image URL like '.../at/2020005521308/HB_500px.jpg'."""
    if not image_url:
        return None
    match = re.search(r"/at/(\d+)/", image_url)
    return match.group(1) if match else None


def _parse_unit_price_text(text):
    """Parse 'Per 1 kg 19,95' → (19.95, 'kg') or return (None, None)."""
    if not text:
        return None, None
    match = re.search(r"Per\s+\d+\s+(\S+?\.?)\s+([\d,.]+)", text)
    if not match:
        return None, None
    unit_raw = match.group(1)
    price_str = match.group(2).replace(",", ".")
    unit = unit_raw.rstrip(".")
    try:
        price = float(price_str)
    except ValueError:
        return None, None
    return price, unit


def _parse_tile(tile, category):
    """Parse a single product-tile element into a product dict."""
    brand_el = tile.query_selector("div.product-tile__name1")
    name_el = tile.query_selector("div.product-tile__name2")
    amount_el = tile.query_selector("div.product-tile__name3")
    price_el = tile.query_selector("span.product-price__price")
    unit_el = tile.query_selector('span[data-tosca="product-price-comparison-price"]')
    img_el = tile.query_selector("img.adaptive-image__img")

    brand = brand_el.inner_text().strip() if brand_el else ""
    name = name_el.inner_text().strip() if name_el else ""
    amount = amount_el.inner_text().strip() if amount_el else ""

    price = None
    if price_el:
        price_text = price_el.inner_text().strip().replace(",", ".")
        try:
            price = float(re.sub(r"[^\d.]", "", price_text))
        except ValueError:
            price = None

    unit_price, unit_label = _parse_unit_price_text(
        unit_el.inner_text().strip() if unit_el else None
    )

    image_url = img_el.get_attribute("src") if img_el else None
    sku = _extract_sku(image_url)
    product_id = f"spar_{sku}" if sku else None

    return {
        "id": product_id,
        "name": name,
        "price": price,
        "originalPrice": None,
        "promotionText": None,
        "unitPrice": unit_price,
        "unitLabel": unit_label,
        "category": category,
        "brand": brand,
        "amount": amount,
        "sku": sku,
        "inPromotion": False,
        "imageUrl": image_url,
        "supermarket": "spar",
    }


def _take_screenshot(page_obj, category, page_num, label):
    """Save a screenshot to SCREENSHOT_DIR for debugging CI failures."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = os.path.join(SCREENSHOT_DIR, f"spar_{category}_p{page_num}_{label}.png")
    try:
        page_obj.screenshot(path=filename, full_page=True)
        print(f"Screenshot saved: {filename}")
    except Exception as e:
        print(f"Failed to save screenshot: {e}")


def _get_total_pages(page):
    """Extract total pages from 'div.pagination__text' e.g. '1 von 11' → 11."""
    pagination = page.query_selector("div.pagination__text")
    if not pagination:
        return 1
    text = pagination.inner_text().strip()
    match = re.search(r"(\d+)\s+von\s+(\d+)", text)
    if not match:
        return 1
    return int(match.group(2))


def _scrape_category(browser, category):
    """Scrape all pages for a single category."""
    context = browser.new_context(user_agent=USER_AGENT)
    page_obj = context.new_page()
    products = []

    try:
        url = BASE_URL.format(category=category, page=1)
        page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_obj.wait_for_selector("div.spar-plp__grid", timeout=30000)

        total_pages = _get_total_pages(page_obj)

        for page_num in range(1, total_pages + 1):
            if page_num > 1:
                url = BASE_URL.format(category=category, page=page_num)
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page_obj.wait_for_selector("div.spar-plp__grid", timeout=30000)
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2
                            print(f"  Retry {attempt + 1}/{max_retries} for page {page_num} (waiting {wait_time}s)...")
                            time.sleep(wait_time)
                        else:
                            _take_screenshot(page_obj, category, page_num, "retry_exhausted")
                            raise

            tiles = page_obj.query_selector_all("article.product-tile")
            for tile in tiles:
                product = _parse_tile(tile, category)
                products.append(product)

            print(f"spar {category} page {page_num}/{total_pages}: {len(tiles)} products")

            if page_num < total_pages:
                page_obj.wait_for_timeout(2000)

    except Exception:
        _take_screenshot(page_obj, category, 0, "failure")
        raise
    finally:
        context.close()

    print(f"spar {category} total: {len(products)} products")
    return products


def scrape_spar():
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

    return all_products
