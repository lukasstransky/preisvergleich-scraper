"""Hofer weekly leaflet (Flugblatt) scraper.

Hofer's online shop API (see ``hofer.py``) only covers the orderable online
assortment. The weekly in-store *Aktionen* live only in the printed leaflet,
which Hofer publishes as a **Publitas flipbook** at https://katalog.hofer.at/.
That flipbook has no structured product data — its interactive hotspots are just
external links (newsletter, contests, travel) — but the downloadable PDF has a
full text layer and, more importantly, clean page images.

This module renders each PDF page to an image and uses **Claude vision**
(``claude-opus-4-8``) to extract structured products (name, price, crossed-out
price, amount, unit price). Results are cached per flipbook slug so the LLM only
runs when a new leaflet is published (roughly weekly), not on every daily cron.

Products carry ``supermarket: "hofer"`` so the app shows them as Hofer offers,
but they are synced under their own ``hofer_flugblatt`` metadata bucket (see
``main.py``) with generated ``hofer_fb_<hash>`` ids that cannot collide with the
online API's ``hofer_<sku>`` ids.
"""

import hashlib
import json
import os
import re
from datetime import date

import requests

from scrapers.categories import normalize_category
from scrapers.tokenizer import tokenize_name

KATALOG_URL = "https://katalog.hofer.at/"
CACHE_DIR = os.environ.get("FLUGBLATT_CACHE_DIR", "flugblatt_cache")
# Anthropic credentials, resolved like firebase_store does: env var first, then a
# local gitignored file. This way extraction works whether main.py is invoked
# directly or through run.sh.
ANTHROPIC_KEY_FILE = ".anthropic_key"
# Vision model for leaflet extraction. Haiku is plenty for OCR-style extraction
# from clean, high-contrast leaflet images and is the cheapest option; bump to
# claude-sonnet-4-6 (or claude-opus-4-8) via HOFER_FLUGBLATT_MODEL if dense
# small-print pages (unit prices) come out unreliable. The LLM only runs when a
# new leaflet is published (~weekly), so cost is a handful of cents per week.
MODEL = os.environ.get("HOFER_FLUGBLATT_MODEL", "claude-haiku-4-5")
RENDER_DPI = 150

# The unified category set produced by scrapers/categories.py normalize_category().
# Claude classifies each product directly into one of these, so leaflet products
# (which carry no source category) still get a useful normalizedCategory.
UNIFIED_CATEGORIES = [
    "Alkohol", "Baby & Tier", "Brot & Gebäck", "Drogerie & Haushalt",
    "Fertiggerichte", "Fleisch & Fisch", "Frühstück & Aufstriche", "Getränke",
    "Grundnahrungsmittel", "Kaffee & Tee", "Milchprodukte", "Obst & Gemüse",
    "Sonstiges", "Süßes & Snacks", "Tiefkühl",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# JSON schema Claude must return for each page image.
_PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "brand": {"type": ["string", "null"]},
                    "price": {"type": ["number", "null"]},
                    "originalPrice": {"type": ["number", "null"]},
                    "amount": {"type": ["string", "null"]},
                    "unitPrice": {"type": ["number", "null"]},
                    "unitLabel": {"type": ["string", "null"]},
                    "promotionText": {"type": ["string", "null"]},
                    "category": {"type": "string", "enum": UNIFIED_CATEGORIES},
                },
                "required": [
                    "name", "brand", "price", "originalPrice",
                    "amount", "unitPrice", "unitLabel", "promotionText", "category",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["products"],
    "additionalProperties": False,
}

_EXTRACT_PROMPT = (
    "Dies ist eine Seite aus dem Hofer (Österreich) Werbe-Flugblatt. "
    "Extrahiere jedes beworbene Lebensmittel-, Getränke- oder Drogerie-/Haushaltsprodukt mit Preis als JSON.\n"
    "- name: Produktname ohne Marke (z. B. 'Emmentaler Scheiben').\n"
    "- brand: Marke, falls erkennbar (z. B. 'Milsani', 'Milka'), sonst null.\n"
    "- price: der aktuelle Aktionspreis in Euro als Zahl (z. B. 4.99). Der große/hervorgehobene Preis.\n"
    "- originalPrice: der durchgestrichene frühere Preis in Euro, falls vorhanden, sonst null.\n"
    "- amount: Füllmenge/Gewicht als Text wie gedruckt (z. B. '250 g', '0,75 l'), sonst null.\n"
    "- unitPrice: Grundpreis-Zahl (z. B. 6.65 bei '6,65/Liter'), sonst null.\n"
    "- unitLabel: Grundpreis-Einheit (z. B. 'Liter', 'kg', '100 g'), sonst null.\n"
    "- promotionText: kurzer Aktionshinweis wie '-33%' oder 'TIEFPREIS AKTION', sonst null.\n"
    "- category: ordne das Produkt genau einer dieser Kategorien zu: "
    + ", ".join(UNIFIED_CATEGORIES) + ".\n\n"
    "Verwende Punkt als Dezimaltrennzeichen. Erfinde keine Werte — was nicht klar lesbar ist, ist null.\n"
    "NUR Verbrauchsgüter aus dem Supermarkt-Sortiment: Lebensmittel, Getränke, Drogerie/Kosmetik, "
    "Reinigungs-/Haushaltsverbrauch (z. B. Waschmittel, Handschuhe, Alufolie), Babynahrung/Windeln/Pflege "
    "und Tierfutter/-bedarf.\n"
    "IGNORIERE strikt alle Gebrauchsartikel und Non-Food, auch wenn sie einen Preis haben — z. B. "
    "Kleidung, Bademode und Schuhe (z. B. Marke 'Lily & Dan'), Spielzeug, Geschirr/Besteck/Küchenutensilien "
    "(z. B. 'Crofton', Disney-Lizenzartikel), Werkzeug, Elektronik/Technik, Möbel/Garten/Deko, "
    "Handytarife (z. B. HoT), Reisen, Gutscheine, Gewinnspiele, Rezepte und reine Werbung ohne Produktpreis. "
    "Die Kategorie 'Baby & Tier' gilt nur für Babynahrung/Windeln/Babypflege und Tierfutter/-bedarf — "
    "NICHT für Kinderkleidung, Kinderbesteck oder Kinderspielzeug (die gehören ausgeschlossen).\n"
    "Wenn die Seite keine passenden Produkte mit Preis zeigt, gib eine leere products-Liste zurück."
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _resolve_api_key():
    """Resolve the Anthropic API key: ``ANTHROPIC_API_KEY`` env var, then ``.anthropic_key``."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    if os.path.exists(ANTHROPIC_KEY_FILE):
        with open(ANTHROPIC_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def _discover_flugblatt():
    """Resolve the current flipbook and its PDF URL.

    katalog.hofer.at redirects to the current flipbook (e.g.
    ``/flipbook_kw28_26_2/``); the flipbook HTML embeds the Publitas PDF URL.

    Returns ``(slug, pdf_url)`` or ``(None, None)`` if discovery fails.
    """
    resp = requests.get(KATALOG_URL, headers=_HEADERS, timeout=30, allow_redirects=True)
    resp.raise_for_status()

    slug_match = re.search(r"flipbook_[a-z0-9_]+", resp.url) or re.search(
        r"flipbook_[a-z0-9_]+", resp.text
    )
    if not slug_match:
        return None, None
    slug = slug_match.group(0)

    flip_url = f"https://katalog.hofer.at/{slug}/"
    page = requests.get(flip_url, headers=_HEADERS, timeout=30)
    page.raise_for_status()

    pdf_match = re.search(
        r"https://view\.publitas\.com/\d+/\d+/pdfs/[a-f0-9-]+\.pdf", page.text
    )
    pdf_url = pdf_match.group(0) if pdf_match else None
    return slug, pdf_url


_WEEKDAY = r"(?:MO|DI|MI|DO|FR|SA|SO)\.?\s*"

# Anchored on the leaflet's own statement of its validity, e.g.
# "Flugblatt gültig ab FR. 10.7. bis DO. 16.7.". Page 1 also carries unrelated
# date ranges (coupon validity, a single product's "PROBIERPREIS VON 10.7. BIS
# 6.8."), so a generic "<date> bis <date>" match picks the wrong pair.
_VALIDITY_RE = re.compile(
    r"Flugblatt\s+gültig\s+ab\s+" + _WEEKDAY + r"?(\d{1,2})\s*\.\s*(\d{1,2})\s*\."
    r"\s*bis\s+" + _WEEKDAY + r"?(\d{1,2})\s*\.\s*(\d{1,2})\s*\.",
    re.IGNORECASE,
)


def _parse_validity(page_text):
    """Parse the leaflet's offer window from its first page.

    Returns ``(offerStart, offerEnd)`` as ISO date strings, or ``(None, None)``
    if the validity line is absent. We deliberately return nothing rather than
    guess — a wrong window is worse than no window for the app.
    """
    m = _VALIDITY_RE.search(page_text)
    if not m:
        return None, None
    year = date.today().year
    try:
        start = date(year, int(m.group(2)), int(m.group(1)))
        end = date(year, int(m.group(4)), int(m.group(3)))
    except ValueError:
        return None, None
    if end < start:
        # Leaflet spans a year boundary (e.g. "ab 27.12. bis 2.1.").
        try:
            end = date(year + 1, int(m.group(4)), int(m.group(3)))
        except ValueError:
            return None, None
    return start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Vision extraction
# ---------------------------------------------------------------------------

def _render_pages(pdf_bytes):
    """Render each PDF page to PNG bytes. Also returns the first page's text."""
    import fitz  # PyMuPDF — imported lazily so the module loads without it.

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    first_text = doc[0].get_text() if doc.page_count else ""
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=RENDER_DPI)
        images.append(pix.tobytes("png"))
    doc.close()
    return images, first_text


def _extract_page(client, png_bytes):
    """Send one page image to Claude and return its list of raw product dicts."""
    import base64

    b64 = base64.standard_b64encode(png_bytes).decode("utf-8")
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                },
                {"type": "text", "text": _EXTRACT_PROMPT},
            ],
        }],
        output_config={"format": {"type": "json_schema", "schema": _PAGE_SCHEMA}},
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        return []
    return json.loads(text).get("products", [])


def _build_product(raw, offer_start, offer_end):
    """Turn one extracted item into the shared product dict, or None if unusable."""
    name = (raw.get("name") or "").strip()
    price = raw.get("price")
    if not name or price is None:
        return None

    brand = (raw.get("brand") or None)
    amount = (raw.get("amount") or None)
    # Stable id from brand+name+amount so the same offer keeps its id across runs.
    key = "|".join(str(x or "").lower().strip() for x in (brand, name, amount))
    pid = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]

    # Prefer the category Claude assigned; fall back to name-based normalization.
    category = raw.get("category")
    if category not in UNIFIED_CATEGORIES:
        category = normalize_category(name)
    return {
        "id": f"hofer_fb_{pid}",
        "name": name,
        "price": round(float(price), 2),
        "originalPrice": round(float(raw["originalPrice"]), 2) if raw.get("originalPrice") is not None else None,
        "promotionText": (raw.get("promotionText") or None),
        "unitPrice": round(float(raw["unitPrice"]), 2) if raw.get("unitPrice") is not None else None,
        "unitLabel": (raw.get("unitLabel") or None),
        "category": None,
        "brand": brand,
        "amount": amount,
        "sku": None,
        "inPromotion": True,
        "imageUrl": None,
        "productUrl": None,
        "offerStart": offer_start,
        "offerEnd": offer_end,
        "supermarket": "hofer",
        "nameTokens": tokenize_name(name),
        "normalizedCategory": category,
        "nameLength": len(name),
    }


def _dedupe(products):
    """Drop duplicate ids (same product printed on multiple pages)."""
    seen = set()
    unique = []
    for p in products:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_path(slug):
    return os.path.join(CACHE_DIR, f"{slug}.json")


def _load_cache(slug):
    path = _cache_path(slug)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(slug, products):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(slug), "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _extract_flugblatt(pdf_bytes, api_key=None):
    """Render the PDF and run vision extraction over every page."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key or _resolve_api_key())
    images, first_text = _render_pages(pdf_bytes)
    offer_start, offer_end = _parse_validity(first_text)

    products = []
    for i, png in enumerate(images, start=1):
        try:
            raw_items = _extract_page(client, png)
        except Exception as e:
            print(f"  hofer flugblatt: page {i} extraction failed: {e}")
            continue
        for raw in raw_items:
            product = _build_product(raw, offer_start, offer_end)
            if product is not None:
                products.append(product)
        print(f"  hofer flugblatt: page {i}/{len(images)} -> {len(raw_items)} items")

    return _dedupe(products)


def scrape_hofer_flugblatt():
    """Scrape the current Hofer leaflet and write ``hofer_flugblatt.json``.

    Cached per flipbook slug: if the current leaflet was already extracted, the
    cached products are reused (no LLM calls). Requires ``ANTHROPIC_API_KEY``;
    without it, extraction is skipped and an empty list is returned.
    """
    print("Starting Hofer Flugblatt scraper...")

    try:
        slug, pdf_url = _discover_flugblatt()
    except Exception as e:
        print(f"hofer flugblatt: discovery failed: {e}")
        slug, pdf_url = None, None

    products = []
    if not slug or not pdf_url:
        print("hofer flugblatt: no current leaflet found, skipping")
    else:
        cached = _load_cache(slug)
        api_key = _resolve_api_key()
        if cached is not None:
            print(f"hofer flugblatt: using cached extraction for {slug} ({len(cached)} products)")
            products = cached
        elif not api_key:
            print(
                f"hofer flugblatt: no Anthropic API key (set ANTHROPIC_API_KEY or create "
                f"{ANTHROPIC_KEY_FILE}), skipping vision extraction for {slug}"
            )
        else:
            print(f"hofer flugblatt: extracting {slug} via {MODEL}...")
            pdf = requests.get(pdf_url, headers=_HEADERS, timeout=120)
            pdf.raise_for_status()
            products = _extract_flugblatt(pdf.content, api_key)
            # Only cache a successful extraction. An empty result means the run
            # failed (API down, rate limit, all pages errored) — don't poison the
            # cache with it, so the next daily run retries instead of returning
            # 0 products for the whole week.
            if products:
                _save_cache(slug, products)
            else:
                print("hofer flugblatt: extraction produced 0 products, not caching (will retry next run)")

    print(f"hofer flugblatt total: {len(products)} products")
    with open("hofer_flugblatt.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(products)} products to hofer_flugblatt.json")

    return products
