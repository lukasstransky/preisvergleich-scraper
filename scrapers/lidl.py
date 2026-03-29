import json
import re
import requests
import time

BASE_URL = "https://www.lidl.at/q/api/search"

# Main "Essen & Trinken" category – the API returns all subcategories within it.
CATEGORY_ID = "10068374"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

PAGE_SIZE = 500
DELAY = 0.5


def _parse_base_price(text):
    """Parse the basePrice text into (unit_price, unit_label).

    Examples:
        'Je 50 g (1 kg = 19.80)'     → (19.80, '€/kg')
        'Je kg'                       → (None, '€/kg')
        'Je 0,75 l (1 l = 4.65)'     → (4.65, '€/l')
        'Ab 2 Stk. je 180 g (1 kg = 5.50)' → (5.50, '€/kg')
        'Je Stk.'                     → (None, '€/Stk')
        '10x 20 g (1 kg = 14.95)'    → (14.95, '€/kg')
    Returns (None, None) when nothing can be extracted.
    """
    if not text:
        return None, None

    unit_map = {
        "kg": "€/kg",
        "l": "€/l",
        "Stk": "€/Stk",
        "Stk.": "€/Stk",
        "100 g": "€/100g",
        "100 ml": "€/100ml",
    }

    # Try to extract "1 kg = 19.80" or "1 l = 4.65" pattern
    match = re.search(r'\(1\s+(kg(?:\s+Abtr\.\s*G\.)?|l|Stk\.?|100\s*(?:g|ml))\s*=\s*([\d.,]+)\)', text)
    if match:
        unit_raw = match.group(1).strip()
        price_str = match.group(2).replace(",", ".")
        # Normalize unit
        if "kg" in unit_raw:
            label = "€/kg"
        elif unit_raw == "l":
            label = "€/l"
        elif "100" in unit_raw and "ml" in unit_raw:
            label = "€/100ml"
        elif "100" in unit_raw and "g" in unit_raw:
            label = "€/100g"
        else:
            label = unit_map.get(unit_raw, f"€/{unit_raw}")
        try:
            unit_price = float(price_str)
            return unit_price, label
        except ValueError:
            pass

    # Fallback: extract unit label from "Je kg", "Je Stk.", "Je l"
    label_match = re.search(r'(?:Je|je)\s+(kg|l|Stk\.?)', text)
    if label_match:
        raw = label_match.group(1).rstrip(".")
        label = unit_map.get(raw, f"€/{raw}")
        return None, label

    return None, None


def _extract_promo_prefix(base_price_text):
    """Extract 'Ab X Stk.' or 'Ab X Fl.' prefix from basePrice text.

    Examples:
        'Ab 2 Stk. je 180 g (1 kg = 5.50)' → 'Ab 2 Stk.'
        'Ab 3 Stk. je 200 g (1 kg = 3.95)' → 'Ab 3 Stk.'
        'Ab 2 Fl. je 0,75 l (1 l = 6.49)'  → 'Ab 2 Fl.'
        'Ab 12 Stk. je 0,33 l (…)'         → 'Ab 12 Stk.'
        'Ab 16 Stk. je 500 g (…)'          → 'Ab 16 Stk.'
        'Je 50 g (1 kg = 19.80)'           → None
    """
    if not base_price_text:
        return None
    m = re.match(r'(Ab\s+\d+\s+(?:Stk|Fl)\.?)', base_price_text)
    return m.group(1).rstrip(".") + "." if m else None


def _parse_product(item):
    """Parse a single search result item. Returns None if required fields missing."""
    try:
        data = item["gridbox"]["data"]
        price_info = data.get("price", {})

        # Primary price – may be absent for Lidl-Plus-only products
        price = price_info.get("price")
        is_lidl_plus = False

        # Fallback: extract price from lidlPlus array
        if price is None:
            lidl_plus = data.get("lidlPlus", [])
            if lidl_plus:
                lp_price_info = lidl_plus[0].get("price", {})
                price = lp_price_info.get("price")
                if price is not None:
                    is_lidl_plus = True
                    # Use lidlPlus price_info as the authoritative source
                    price_info = lp_price_info

        if price is None:
            return None

        product_id = data.get("productId") or data.get("erpNumber")
        sku = str(product_id)

        old_price = price_info.get("oldPrice")
        original_price = old_price if old_price and old_price > 0 else None

        # Also check discount.deletedPrice as original price
        discount = price_info.get("discount") or {}
        deleted_price = discount.get("deletedPrice")
        if original_price is None and deleted_price and deleted_price > 0:
            original_price = deleted_price

        # Build promotion text: combine discount text + "Ab X Stk." prefix
        discount_text = discount.get("discountText") if discount else None
        base_price_text = price_info.get("basePrice", {}).get("text", "")
        promo_prefix = _extract_promo_prefix(base_price_text)

        promo_parts = []
        if discount_text:
            promo_parts.append(discount_text)
        if promo_prefix:
            promo_parts.append(promo_prefix)
        if is_lidl_plus:
            lp_text = data.get("lidlPlus", [{}])[0].get("lidlPlusText", "")
            if lp_text and lp_text not in promo_parts:
                promo_parts.append(lp_text)
        promo_text = ", ".join(promo_parts) if promo_parts else None

        unit_price, unit_label = _parse_base_price(base_price_text)

        brand_info = data.get("brand")
        brand = brand_info.get("name") if brand_info and brand_info.get("name") else None

        # Category from breadcrumbs: pick the most specific (last) entry
        meta = item["gridbox"].get("meta", {})
        breadcrumbs = meta.get("wonCategoryBreadcrumbs", [[]])
        if breadcrumbs and breadcrumbs[0]:
            category = breadcrumbs[0][-1].get("name", "")
        else:
            category = data.get("category", "")

        image = data.get("image", None)

        # Every product on this page is an in-store promotion ("Angebote in deiner
        # Filiale"), so inPromotion is always True.
        in_promotion = True

        return {
            "id": f"lidl_{sku}",
            "name": data.get("fullTitle"),
            "price": price,
            "originalPrice": original_price,
            "promotionText": promo_text,
            "unitPrice": unit_price,
            "unitLabel": unit_label,
            "category": category,
            "brand": brand,
            "sku": sku,
            "inPromotion": in_promotion,
            "imageUrl": image,
            "supermarket": "lidl",
        }
    except (KeyError, TypeError):
        return None


def _scrape_category(category_id):
    """Scrape all products for a category with pagination."""
    products = []
    offset = 0

    while True:
        params = {
            "assortment": "AT",
            "locale": "de_AT",
            "version": "v2.0.0",
            "sort": "relevancy",
            "category.id": category_id,
            "offset": offset,
            "limit": PAGE_SIZE,
        }

        response = requests.get(BASE_URL, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        for item in items:
            parsed = _parse_product(item)
            if parsed is not None:
                products.append(parsed)

        num_found = data.get("numFound", 0)
        fetched = offset + len(items)

        if fetched >= num_found or not items:
            break

        offset = fetched
        time.sleep(DELAY)

    return products


def scrape_lidl():
    """Scrape all Essen & Trinken products and write to lidl.json."""
    all_products = []

    try:
        products = _scrape_category(CATEGORY_ID)
        all_products.extend(products)
        print(f"lidl essen-trinken: {len(products)} products")
    except Exception as e:
        print(f"Error scraping Lidl: {e}")

    print(f"lidl total: {len(all_products)} products")

    with open("lidl.json", "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_products)} products to lidl.json")

    return all_products
