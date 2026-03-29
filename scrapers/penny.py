import json
import re
import requests
import time
from datetime import date

from scrapers.tokenizer import tokenize_name
from scrapers.categories import normalize_category

BASE_URL = "https://www.penny.at/api/product-discovery/categories/{category}/products"

OFFERS_URL = "https://www.penny.at/angebote"
MAX_OFFER_AGE_DAYS = 14

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

PAGE_SIZE = 500
DELAY = 0.5


def _parse_product(product):
    """Parse a single product dict. Returns None if required fields are missing."""
    try:
        price_info = product["price"]
        price_data = price_info["regular"]
        sku = product.get("sku")
        crossed = price_info.get("crossed")
        per_qty = price_data.get("perStandardizedQuantity")
        return {
            "id": f"penny_{sku}",
            "name": product.get("name"),
            "price": price_data["value"] / 100,
            "originalPrice": crossed / 100 if crossed is not None else None,
            "promotionText": price_data.get("promotionText", None),
            "unitPrice": per_qty / 100 if per_qty is not None else None,
            "unitLabel": price_info.get("baseUnitShort"),
            "category": product.get("category"),
            "brand": product.get("brand", {}).get("name") if product.get("brand") else None,
            "sku": sku,
            "inPromotion": product.get("inPromotion", False),
            "imageUrl": product["images"][0] if product.get("images") else None,
            "supermarket": "penny",
            "nameTokens": tokenize_name(product.get("name")),
            "normalizedCategory": normalize_category(product.get("category")),
            "nameLength": len(product.get("name", "") or ""),
        }
    except (KeyError, TypeError):
        return None


def _scrape_category(category):
    """Scrape all products for a single category with pagination."""
    url = BASE_URL.format(category=category)
    products = []
    page = 0

    while True:
        params = {
            "sortBy": "relevance",
            "enableStatistics": "false",
            "enablePersonalization": "false",
            "pageSize": PAGE_SIZE,
            "page": page,
        }

        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        for item in data.get("results", []):
            parsed = _parse_product(item)
            if parsed is not None:
                products.append(parsed)

        offset = data.get("offset", 0)
        count = data.get("count", 0)
        total = data.get("total", 0)

        if offset + count >= total:
            break

        page += 1
        time.sleep(DELAY)

    return products


def _fetch_offer_tabs():
    """Fetch the Penny offers page and extract tab slugs with their dates.

    Returns a list of (date, api_slug) tuples, e.g.
    (date(2026, 3, 19), 'angebote-ab-1903').
    """
    response = requests.get(OFFERS_URL, headers=HEADERS)
    response.raise_for_status()
    html = response.text

    # Tab links look like: ?tab=angebote-ab-19-03
    matches = re.findall(r'tab=angebote-ab-(\d{2})-(\d{2})', html)
    today = date.today()
    tabs = []
    seen = set()

    for day_str, month_str in matches:
        key = f"{day_str}{month_str}"
        if key in seen:
            continue
        seen.add(key)

        day, month = int(day_str), int(month_str)
        try:
            offer_date = date(today.year, month, day)
        except ValueError:
            continue

        api_slug = f"angebote-ab-{day_str}{month_str}"
        tabs.append((offer_date, api_slug))

    tabs.sort(key=lambda x: x[0], reverse=True)
    return tabs


def _get_live_offer_tabs():
    """Return only offer tabs that are live: date <= today and not older than MAX_OFFER_AGE_DAYS."""
    today = date.today()
    all_tabs = _fetch_offer_tabs()
    live = []
    for d, slug in all_tabs:
        if d > today:
            print(f"  skipping future tab: {slug} ({d})")
        elif (today - d).days > MAX_OFFER_AGE_DAYS:
            print(f"  skipping stale tab:  {slug} ({d})")
        else:
            print(f"  live tab: {slug} ({d})")
            live.append((d, slug))
    return live


def _scrape_offers():
    """Scrape products from all live offer tabs."""
    live_tabs = _get_live_offer_tabs()
    all_offer_products = []

    for offer_date, slug in live_tabs:
        try:
            products = _scrape_category(slug)
            for p in products:
                p["inPromotion"] = True
            all_offer_products.extend(products)
            print(f"penny offers {slug}: {len(products)} products")
        except Exception as e:
            print(f"Error scraping offer tab '{slug}': {e}")

    return all_offer_products


def scrape_penny():
    """Scrape all live offer tabs and write products to penny.json."""
    all_products = _scrape_offers()

    print(f"penny total: {len(all_products)} products")

    with open("penny.json", "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_products)} products to penny.json")

    return all_products
