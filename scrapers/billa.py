import requests
import time

BASE_URL = "https://www.billa.at/api/product-discovery/categories/{category}/products"

CATEGORIES = [
    "neu-im-online-shop-14506",
    "obst-und-gemuese-13751",
    "brot-und-gebaeck-15520",
    "fleisch-wurst-und-fisch-15388",
    "kuehlwaren-15416",
    "schnelle-kueche-15389",
    "platten-broetchen-und-co-15409",
    "getraenke-13784",
    "vorratsschrank-15012",
    "tiefkuehl-15415",
    "rein-pflanzlich-15207",
    "drogerie-und-kosmetik-15274",
    "kueche-haushalt-und-garten-15320",
    "baby-und-kleinkind-15671",
    "haustier-15672",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

PAGE_SIZE = 500
DELAY = 0.5


def _parse_product(product):
    """Parse a single product dict. Returns None if required fields are missing."""
    try:
        price_data = product["price"]["regular"]
        return {
            "name": product.get("name"),
            "price": price_data["value"] / 100,
            "unitPrice": price_data.get("perStandardizedQuantity", 0) / 100 if price_data.get("perStandardizedQuantity") is not None else None,
            "unitLabel": product.get("price", {}).get("baseUnitShort"),
            "category": product.get("category"),
            "brand": product.get("brand", {}).get("name") if product.get("brand") else None,
            "sku": product.get("sku"),
            "inPromotion": product.get("inPromotion", False),
            "imageUrl": product["images"][0] if product.get("images") else None,
            "supermarket": "billa",
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


def scrape_billa():
    """Scrape all categories and return a dict mapping category → list of products."""
    results = {}

    for category in CATEGORIES:
        try:
            products = _scrape_category(category)
            results[category] = products
        except Exception as e:
            print(f"Error scraping category '{category}': {e}")
            results[category] = []

    return results
