import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from playwright.async_api import async_playwright

SCREENSHOT_DIR = "screenshots"

BASE_URL = "https://www.spar.at/produktwelt/{category}"

CATEGORIES = [
    "obst-gemuese",
    #"brot-gebaeck",
    #"milchprodukte-alternativen",
    #"tiefkuehlprodukte",
    #"wurst-fleisch-eier-fisch",
    #"beilagen-essig-oel-gewuerze",
    #"backen-fruehstueck",
    #"suesses-salziges",
    #"schnelle-kueche-to-go",
    #"babynahrung",
    #"alkoholfreie-getraenke",
    #"kaffee-tee-kakao",
    #"alkoholische-getraenke",
]

MAX_CONCURRENT = 2
PAGE_RETRY_LIMIT = 5
CATEGORY_RETRY_LIMIT = 3

ERROR_LOG_FILE = "spar_errors.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _extract_sku(url):
    """Extract SKU (long digit sequence) from a URL.

    Works with image URLs like '.../at/2020005521308/HB_500px.jpg'
    and product-page URLs like '/produkte/spar-premium-xyz-2020005521308/'.
    """
    if not url:
        return None
    # Try the /at/<digits>/ pattern first (image URLs)
    match = re.search(r"/at/(\d{7,})/", url)
    if match:
        return match.group(1)
    # Try a long digit sequence at the end of a URL path segment (product links).
    # Handles both '-<digits>' and '-p<digits>' suffixes (e.g. '-p2020003543821').
    match = re.search(r"[/-]p?(\d{7,})(?:[/?#]|$)", url)
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


async def _parse_tile(tile, category):
    """Parse a single product-tile element into a product dict."""
    brand_el = await tile.query_selector("div.product-tile__name1")
    name_el = await tile.query_selector("div.product-tile__name2")
    amount_el = await tile.query_selector("div.product-tile__name3")
    price_el = await tile.query_selector("span.product-price__price")
    unit_el = await tile.query_selector('span[data-tosca="product-price-comparison-price"]')
    img_el = await tile.query_selector("img.adaptive-image__img")
    link_el = await tile.query_selector('a[href*="/produktwelt/"]') or await tile.query_selector("a[href]")

    brand = (await brand_el.inner_text()).strip() if brand_el else ""
    name = (await name_el.inner_text()).strip() if name_el else ""
    amount = (await amount_el.inner_text()).strip() if amount_el else ""

    price = None
    if price_el:
        price_text = (await price_el.inner_text()).strip().replace(",", ".")
        try:
            price = float(re.sub(r"[^\d.]", "", price_text))
        except ValueError:
            price = None

    unit_price, unit_label = _parse_unit_price_text(
        (await unit_el.inner_text()).strip() if unit_el else None
    )

    # Resolve image URL: prefer src, fall back to data-src / srcset for lazy-loaded images
    image_url = None
    if img_el:
        image_url = await img_el.get_attribute("src")
        if not _extract_sku(image_url):
            data_src = await img_el.get_attribute("data-src")
            srcset_parts = (await img_el.get_attribute("srcset") or "").split()
            image_url = data_src or (srcset_parts[0] if srcset_parts else None) or image_url

    link_href = await link_el.get_attribute("href") if link_el else None

    # Prefer link href (always in initial HTML, never lazy-loaded) over image URL
    sku = _extract_sku(link_href) or _extract_sku(image_url)

    # Fallback: generate a stable ID from name + brand + category when SKU is missing
    if sku:
        product_id = f"spar_{sku}"
    else:
        hash_input = f"{brand}|{name}|{category}".lower()
        fallback_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        product_id = f"spar_hash_{fallback_hash}"

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


async def _dismiss_cookie_banner(page_obj):
    """Try to dismiss consentmanager cookie banner (renders in Shadow DOM)."""
    try:
        btn = page_obj.locator("a.cmpboxbtnyes").first
        await btn.wait_for(state="visible", timeout=5000)
        await btn.click()
        await page_obj.wait_for_timeout(500)
    except Exception:
        pass


async def _take_screenshot(page_obj, category, page_num, label):
    """Save a screenshot to SCREENSHOT_DIR for debugging CI failures."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = os.path.join(SCREENSHOT_DIR, f"spar_{category}_p{page_num}_{label}.png")
    try:
        await page_obj.screenshot(path=filename, full_page=True)
        print(f"Screenshot saved: {filename}")
    except Exception as e:
        print(f"Failed to save screenshot: {e}")


async def _get_total_pages(page):
    """Extract total pages from 'div.pagination__text' e.g. '1 von 11' → 11."""
    pagination = await page.query_selector("div.pagination__text")
    if not pagination:
        return 1
    text = (await pagination.inner_text()).strip()
    match = re.search(r"(\d+)\s+von\s+(\d+)", text)
    if not match:
        return 1
    return int(match.group(2))


async def _is_search_broken(page_obj):
    """Return True if the page shows the 'Leider funktioniert unsere Suche' error."""
    try:
        tiles = await page_obj.query_selector_all("article.product-tile")
        if tiles:
            return False
        body_text = await page_obj.inner_text("body")
        return "Leider funktioniert unsere Suche" in body_text or "0 Ergebnisse" in body_text
    except Exception:
        return False


async def _get_current_page_num(page_obj):
    """Extract current page number from pagination text, e.g. '3 von 11' → 3."""
    pagination = await page_obj.query_selector("div.pagination__text")
    if not pagination:
        return 1
    text = (await pagination.inner_text()).strip()
    match = re.search(r"(\d+)\s+von\s+\d+", text)
    return int(match.group(1)) if match else 1


async def _load_page(page_obj, url, category, page_num):
    """Navigate to a URL, dismiss cookies, wait for the grid, and retry on search errors."""
    for attempt in range(PAGE_RETRY_LIMIT):
        await page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _dismiss_cookie_banner(page_obj)

        try:
            await page_obj.wait_for_selector("div.spar-plp__grid", timeout=15000)
        except Exception:
            pass

        if not await _is_search_broken(page_obj):
            return

        if attempt < PAGE_RETRY_LIMIT - 1:
            wait = 3 * (attempt + 1)
            print(f"  Search broken for {category} p{page_num}, retry {attempt + 1}/{PAGE_RETRY_LIMIT} in {wait}s...")
            await asyncio.sleep(wait)
        else:
            await _take_screenshot(page_obj, category, page_num, "search_broken")
            raise RuntimeError(f"Spar search broken for {category} page {page_num} after {PAGE_RETRY_LIMIT} retries")


async def _click_next_page(page_obj, expected_page_num):
    """Click the 'next page' button and wait for the pagination text to update.

    Returns True if navigation succeeded, False if there is no next button.
    """
    next_btn = page_obj.locator('button[data-tosca="plp-pagination-next-btn"]')
    try:
        await next_btn.wait_for(state="visible", timeout=5000)
    except Exception:
        return False

    if await next_btn.is_disabled():
        return False

    await next_btn.click()

    # Wait for the pagination text to reflect the new page number
    try:
        await page_obj.wait_for_function(
            f"document.querySelector('div.pagination__text')?.innerText.trim().startsWith('{expected_page_num} ')",
            timeout=15000,
        )
    except Exception:
        pass

    # Also wait for the product grid to be present
    try:
        await page_obj.wait_for_selector("div.spar-plp__grid", timeout=10000)
    except Exception:
        pass

    # Small extra settle time for DOM rendering
    await page_obj.wait_for_timeout(500)
    return True


async def _scrape_category(browser, category, semaphore, error_log):
    """Scrape all pages for a single category, with retry and skip logic."""
    async with semaphore:
        for cat_attempt in range(CATEGORY_RETRY_LIMIT):
            context = await browser.new_context(user_agent=USER_AGENT)
            page_obj = await context.new_page()
            products = []
            seen_ids = set()
            skipped_pages = []

            try:
                url = BASE_URL.format(category=category)
                try:
                    await _load_page(page_obj, url, category, 1)
                except RuntimeError as e:
                    msg = f"Page 1 load failed for {category}: {e}"
                    print(f"  {msg}")
                    error_log.append({"type": "page_skip", "category": category, "page": 1, "error": str(e)})
                    skipped_pages.append(1)
                    # Page 1 broken means we can't get total_pages — retry the whole category
                    await context.close()
                    if cat_attempt < CATEGORY_RETRY_LIMIT - 1:
                        wait = 5 * (cat_attempt + 1)
                        print(f"  Retrying category {category} (attempt {cat_attempt + 2}/{CATEGORY_RETRY_LIMIT}) in {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        error_log.append({"type": "category_fail", "category": category, "error": f"Page 1 broken after {CATEGORY_RETRY_LIMIT} category retries"})
                        return []

                total_pages = await _get_total_pages(page_obj)

                # Check if page 1 returned 0 products — retry the category
                tiles = await page_obj.query_selector_all("article.product-tile")
                if len(tiles) == 0:
                    msg = f"Page 1 returned 0 products for {category}"
                    print(f"  {msg}")
                    error_log.append({"type": "empty_page1_retry", "category": category, "attempt": cat_attempt + 1})
                    await context.close()
                    if cat_attempt < CATEGORY_RETRY_LIMIT - 1:
                        wait = 5 * (cat_attempt + 1)
                        print(f"  Retrying category {category} (attempt {cat_attempt + 2}/{CATEGORY_RETRY_LIMIT}) in {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        error_log.append({"type": "category_fail", "category": category, "error": f"Page 1 still empty after {CATEGORY_RETRY_LIMIT} category retries"})
                        return []

                # Page 1 had products — parse them
                new_count = 0
                for tile in tiles:
                    product = await _parse_tile(tile, category)
                    if product["id"] not in seen_ids:
                        seen_ids.add(product["id"])
                        products.append(product)
                        new_count += 1
                print(f"spar {category} page 1/{total_pages}: {len(tiles)} products ({new_count} new)")

                # Scrape remaining pages by clicking the "next page" button
                for page_num in range(2, total_pages + 1):
                    try:
                        navigated = await _click_next_page(page_obj, page_num)
                        if not navigated:
                            print(f"  No next-page button on page {page_num - 1}, stopping pagination for {category}")
                            break
                    except Exception as e:
                        msg = f"Skipping {category} page {page_num}: {e}"
                        print(f"  {msg}")
                        error_log.append({"type": "page_skip", "category": category, "page": page_num, "error": str(e)})
                        skipped_pages.append(page_num)
                        break

                    # Verify we actually moved to the expected page
                    actual_page = await _get_current_page_num(page_obj)
                    if actual_page != page_num:
                        print(f"  Expected page {page_num} but got {actual_page}, stopping pagination for {category}")
                        break

                    tiles = await page_obj.query_selector_all("article.product-tile")
                    new_count = 0
                    for tile in tiles:
                        product = await _parse_tile(tile, category)
                        if product["id"] not in seen_ids:
                            seen_ids.add(product["id"])
                            products.append(product)
                            new_count += 1

                    print(f"spar {category} page {page_num}/{total_pages}: {len(tiles)} products ({new_count} new)")

            except Exception as e:
                await _take_screenshot(page_obj, category, 0, "failure")
                error_log.append({"type": "category_exception", "category": category, "error": str(e)})
                await context.close()
                raise
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

            if skipped_pages:
                error_log.append({"type": "pages_skipped_summary", "category": category, "skipped_pages": skipped_pages, "count": len(skipped_pages)})

            null_skus = sum(1 for p in products if p["sku"] is None)
            print(f"spar {category} total: {len(products)} products ({null_skus} with null SKU)")
            return products

        # Should not reach here, but just in case
        return []


async def _scrape_spar_async():
    """Scrape all categories concurrently and write products to spar.json."""
    all_products = []
    error_log = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            tasks = [
                _scrape_category(browser, category, semaphore, error_log)
                for category in CATEGORIES
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for category, result in zip(CATEGORIES, results):
                if isinstance(result, Exception):
                    msg = f"Error scraping category '{category}': {result}"
                    print(msg)
                    error_log.append({"type": "category_exception", "category": category, "error": str(result)})
                else:
                    all_products.extend(result)
        finally:
            await browser.close()

    with open("spar.json", "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    null_skus = sum(1 for p in all_products if p["sku"] is None)
    print(f"Saved {len(all_products)} products to spar.json ({null_skus} with null SKU)")

    # Write error log
    error_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_errors": len(error_log),
        "errors": error_log,
    }
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(error_summary, f, ensure_ascii=False, indent=2)
    if error_log:
        print(f"Wrote {len(error_log)} error(s) to {ERROR_LOG_FILE}")
    else:
        print(f"No errors encountered (wrote empty log to {ERROR_LOG_FILE})")

    return all_products


def scrape_spar():
    """Scrape all categories and write products to spar.json."""
    return asyncio.run(_scrape_spar_async())
