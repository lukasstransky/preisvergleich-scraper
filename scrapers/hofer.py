import json
import re

import requests

from scrapers.categories import normalize_category
from scrapers.tokenizer import tokenize_name

PRODUCT_SEARCH_URL = "https://asl.api.hofer.at/commerce/v3/product-search"

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-AT",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.hofer.at/",
    "Origin": "https://www.hofer.at",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}

_BASE_PARAMS = {
    "currency": "EUR",
    "serviceType": "walk-in",
    "limit": 60,
    "sort": "relevance",
}

_PROMO_CATEGORIES = {"HOFER PREISWOCHEN", "HOFER Preis - Dauerhaft Günstiger"}


def _parse_comparison_price(display: str | None) -> tuple[float | None, str | None]:
    """Parse '(€ 1,88/1 kg)' → (1.88, 'kg')."""
    if not display:
        return None, None
    m = re.search(r"€\s*([\d]+[,.][\d]+)\s*/\s*(?:\d+\s*)?([\w]+)", display)
    if not m:
        return None, None
    try:
        price = float(m.group(1).replace(",", "."))
    except ValueError:
        return None, None
    return price, m.group(2).strip()


def _parse_was_price(display: str | None) -> float | None:
    """Parse '€ 1,89' → 1.89."""
    if not display:
        return None
    m = re.search(r"€\s*([\d]+[,.][\d]+)", display)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _image_url(assets: list) -> str | None:
    """Build an image URL from the first API asset template."""
    if not assets:
        return None
    url = assets[0].get("url", "")
    if not url:
        return None
    display_name = assets[0].get("displayName") or assets[0].get("alt") or "product"
    return url.replace("{width}", "300").replace("{slug}", display_name)


def _parse_product(item: dict) -> dict:
    sku = item["sku"]
    name = item["name"]
    brand = item.get("brandName") or None

    price_data = item.get("price") or {}
    amount_cents = price_data.get("amountRelevant")
    price = amount_cents / 100 if amount_cents is not None else None
    original_price = _parse_was_price(price_data.get("wasPriceDisplay"))
    unit_price, unit_label = _parse_comparison_price(price_data.get("comparisonDisplay"))

    amount = item.get("sellingSize") or None
    categories = item.get("categories") or []
    raw_category = categories[0]["name"] if categories else None

    in_promotion = (original_price is not None) or any(
        c["name"] in _PROMO_CATEGORIES for c in categories
    )

    slug = item.get("urlSlugText", "")
    product_url = f"https://www.hofer.at/produkt/{slug}-{sku}" if slug else None

    normalized = normalize_category(raw_category)
    if normalized == "Sonstiges" and not raw_category:
        # API returned no categories for this product — try to infer from name
        normalized = normalize_category(name)

    return {
        "id": f"hofer_{sku}",
        "name": name,
        "price": price,
        "originalPrice": original_price,
        "promotionText": "Preiswoche" if any(c["name"] == "HOFER PREISWOCHEN" for c in categories) else None,
        "unitPrice": unit_price,
        "unitLabel": unit_label,
        "category": raw_category,
        "brand": brand,
        "amount": amount,
        "sku": sku,
        "inPromotion": in_promotion,
        "imageUrl": _image_url(item.get("assets") or []),
        "productUrl": product_url,
        "offerStart": None,
        "offerEnd": None,
        "supermarket": "hofer",
        "nameTokens": tokenize_name(name),
        "normalizedCategory": normalized,
        "nameLength": len(name or ""),
    }


def _fetch_all_products() -> list[dict]:
    """Paginate through all Hofer products and return parsed product dicts."""
    all_products = []
    offset = 0

    while True:
        params = {**_BASE_PARAMS, "offset": offset}
        response = requests.get(PRODUCT_SEARCH_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()

        items = data.get("data") or []
        if not items:
            break

        for item in items:
            all_products.append(_parse_product(item))

        pagination = data["meta"]["pagination"]
        offset += pagination["limit"]
        if offset >= pagination["totalCount"]:
            break

    return all_products


def scrape_hofer() -> list[dict]:
    """Scrape all Hofer products via the REST API and return a product list."""
    print("Starting Hofer scraper...")

    products = _fetch_all_products()

    # Deduplicate by SKU (the API shouldn't return duplicates, but be safe)
    seen = set()
    unique = []
    for p in products:
        if p["sku"] not in seen:
            seen.add(p["sku"])
            unique.append(p)

    duplicates = len(products) - len(unique)
    print(f"hofer total: {len(unique)} products ({duplicates} duplicates removed)")

    with open("hofer.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique)} products to hofer.json")

    return unique
