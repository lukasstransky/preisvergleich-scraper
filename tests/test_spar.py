import asyncio
import hashlib
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from scrapers.spar import (
    _extract_sku,
    _parse_unit_price_text,
    _scrape_category,
    _scrape_spar_async,
    CATEGORY_RETRY_LIMIT,
    PAGE_RETRY_LIMIT,
    ERROR_LOG_FILE,
)


# ---------------------------------------------------------------------------
# Helpers for async tests
# ---------------------------------------------------------------------------

_product_counter = 0


def _make_product(category="obst-gemuese", sku=None, name="Bio Apfel"):
    """Return a minimal product dict matching _parse_tile output.

    Each call returns a product with a unique SKU/ID so that deduplication
    in the scraper does not collapse multiple tiles into one.
    """
    global _product_counter
    _product_counter += 1
    if sku is None:
        sku = f"20200055{_product_counter:05d}"
    return {
        "id": f"spar_{sku}" if sku else f"spar_hash_abc123",
        "name": name,
        "price": 1.99,
        "originalPrice": None,
        "promotionText": None,
        "unitPrice": None,
        "unitLabel": None,
        "category": category,
        "brand": "SPAR",
        "amount": "1 kg",
        "sku": sku,
        "inPromotion": False,
        "imageUrl": None,
        "supermarket": "spar",
    }


def _make_mock_browser(tiles_per_call=None, pagination_text="1 von 1"):
    """Create a mock browser with configurable tile counts per query_selector_all call.

    tiles_per_call: list of ints — number of tiles to return for each
                    successive call to query_selector_all.
                    If None, defaults to [3] (single page with 3 tiles).

    The mock page also supports button-click pagination:
    - ``page.locator(...)`` returns a mock next-page button that is visible and enabled
    - ``page.query_selector('div.pagination__text')`` updates its text after each
      "click" so that ``_get_current_page_num`` returns the expected page number.
    """
    if tiles_per_call is None:
        tiles_per_call = [3]

    tile_iter = iter(tiles_per_call)

    async def mock_query_selector_all(selector):
        if "product-tile" in selector:
            try:
                count = next(tile_iter)
            except StopIteration:
                count = 0
            return [MagicMock() for _ in range(count)]
        return []

    mock_page = AsyncMock()
    mock_page.query_selector_all = mock_query_selector_all

    # Track current page number for pagination text updates
    page_state = {"current": 1}

    # Parse total pages from the initial text
    import re as _re
    _m = _re.search(r"(\d+)\s+von\s+(\d+)", pagination_text)
    total_pages = int(_m.group(2)) if _m else 1

    # Pagination text mock – returns text reflecting current page
    pagination_el = AsyncMock()

    async def _pagination_inner_text():
        return f"{page_state['current']} von {total_pages}"

    pagination_el.inner_text = _pagination_inner_text

    async def mock_query_selector(selector):
        if "pagination__text" in selector:
            return pagination_el
        return None

    mock_page.query_selector = mock_query_selector

    # Next-page button mock for _click_next_page
    mock_next_btn = AsyncMock()
    mock_next_btn.wait_for = AsyncMock()  # visible
    mock_next_btn.is_disabled = AsyncMock(return_value=False)

    async def _mock_click():
        page_state["current"] += 1

    mock_next_btn.click = _mock_click

    def mock_locator(selector):
        if "plp-pagination-next-btn" in selector:
            return mock_next_btn
        return AsyncMock()

    mock_page.locator = mock_locator
    mock_page.wait_for_function = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    return mock_browser, mock_context, mock_page


# ---------------------------------------------------------------------------
# _extract_sku
# ---------------------------------------------------------------------------

class TestExtractSku:
    def test_valid_url(self):
        url = "https://assets.spar.at/at/2020005521308/HB_500px.jpg"
        assert _extract_sku(url) == "2020005521308"

    def test_different_sku(self):
        url = "https://assets.spar.at/at/1234567890123/image.jpg"
        assert _extract_sku(url) == "1234567890123"

    def test_no_match(self):
        url = "https://example.com/image.jpg"
        assert _extract_sku(url) is None

    def test_none_input(self):
        assert _extract_sku(None) is None

    def test_empty_string(self):
        assert _extract_sku("") is None

    def test_placeholder_image_url(self):
        """Placeholder images without a numeric SKU should return None."""
        url = "https://cdn1.interspar.at/cachableservlets/graficImage.dam/at/produktweltBIO/HB_105px.png"
        assert _extract_sku(url) is None

    def test_product_link_url(self):
        """SKU can be extracted from a product page link."""
        url = "/produkte/spar-premium-batavia-rot-300g-2020005521308/"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_url_with_query(self):
        url = "/produkte/spar-premium-xyz-2020005521308?page=2"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_url_slash_separated(self):
        url = "/onlineshop/r/some-name/p/2020005521308"
        assert _extract_sku(url) == "2020005521308"

    def test_product_link_with_p_prefix(self):
        """SKU preceded by '-p' in produktwelt URLs."""
        url = "/produktwelt/spar-premium-weinviertler-beilagen-erdaepfel-vorwiegend-festkochend-p2020003543821"
        assert _extract_sku(url) == "2020003543821"

    def test_product_link_with_p_prefix_and_trailing_slash(self):
        url = "/produktwelt/spar-natur-pur-bio-apfel-p2020004977113/"
        assert _extract_sku(url) == "2020004977113"

    def test_cdn_image_url(self):
        """CDN image URLs from interspar.at."""
        url = "https://cdn1.interspar.at/cachableservlets/articleImage.dam/at/2020004977113/HB_500px.jpg"
        assert _extract_sku(url) == "2020004977113"

    def test_cdn_image_url_short_sku(self):
        url = "https://cdn1.interspar.at/cachableservlets/articleImage.dam/at/6737634/HB_500px.jpg"
        assert _extract_sku(url) == "6737634"

    def test_p_prefix_not_greedy(self):
        """Only one 'p' should be stripped, not part of the SKU."""
        url = "/produktwelt/some-product-p1234567"
        assert _extract_sku(url) == "1234567"


# ---------------------------------------------------------------------------
# _parse_unit_price_text
# ---------------------------------------------------------------------------

class TestParseUnitPriceText:
    def test_per_kg(self):
        price, unit = _parse_unit_price_text("Per 1 kg 19,95")
        assert price == 19.95
        assert unit == "kg"

    def test_per_liter(self):
        price, unit = _parse_unit_price_text("Per 1 l 2,50")
        assert price == 2.50
        assert unit == "l"

    def test_per_100g(self):
        price, unit = _parse_unit_price_text("Per 100 g. 0,99")
        assert price == 0.99
        assert unit == "g"

    def test_none_input(self):
        price, unit = _parse_unit_price_text(None)
        assert price is None
        assert unit is None

    def test_empty_string(self):
        price, unit = _parse_unit_price_text("")
        assert price is None
        assert unit is None

    def test_no_match(self):
        price, unit = _parse_unit_price_text("some random text")
        assert price is None
        assert unit is None

    def test_dot_stripped_from_unit(self):
        price, unit = _parse_unit_price_text("Per 1 kg. 5,00")
        assert price == 5.00
        assert unit == "kg"


# ---------------------------------------------------------------------------
# Fallback hash ID
# ---------------------------------------------------------------------------

class TestFallbackHashId:
    """Verify that the hash-based fallback ID is stable and deterministic."""

    def _make_hash_id(self, brand, name, category):
        hash_input = f"{brand}|{name}|{category}".lower()
        return f"spar_hash_{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"

    def test_deterministic(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        assert id1 == id2

    def test_different_products_differ(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("SPAR", "Bio Birnen", "obst-gemuese")
        assert id1 != id2

    def test_case_insensitive(self):
        id1 = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        id2 = self._make_hash_id("spar", "bio äpfel", "obst-gemuese")
        assert id1 == id2

    def test_prefix(self):
        fid = self._make_hash_id("SPAR", "Bio Äpfel", "obst-gemuese")
        assert fid.startswith("spar_hash_")
        assert len(fid) == len("spar_hash_") + 12


# ---------------------------------------------------------------------------
# _scrape_category – retry on page 1 empty
# ---------------------------------------------------------------------------

class TestScrapeCategoryPage1Empty:
    """When page 1 returns 0 product tiles, the category should be retried."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_retries_on_empty_page1_then_succeeds(self, mock_load, mock_parse, mock_sleep):
        """Category retried when first attempt has 0 tiles, second attempt succeeds."""
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        # First call: page with 0 tiles; second call: page with 2 tiles
        browser, _, _ = _make_mock_browser(tiles_per_call=[0, 2], pagination_text="1 von 1")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 2
        # Should have logged the empty_page1_retry
        retry_errors = [e for e in error_log if e["type"] == "empty_page1_retry"]
        assert len(retry_errors) == 1
        assert retry_errors[0]["attempt"] == 1

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_all_retries_fail_returns_empty(self, mock_load, mock_parse, mock_sleep):
        """All category retry attempts return 0 tiles → returns [] and logs failure."""
        # All attempts return 0 tiles
        browser, _, _ = _make_mock_browser(
            tiles_per_call=[0] * CATEGORY_RETRY_LIMIT,
            pagination_text="1 von 1",
        )
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert result == []
        fail_errors = [e for e in error_log if e["type"] == "category_fail"]
        assert len(fail_errors) == 1
        assert "empty" in fail_errors[0]["error"].lower()


# ---------------------------------------------------------------------------
# _scrape_category – retry on page 1 load error
# ---------------------------------------------------------------------------

class TestScrapeCategoryPage1LoadError:
    """When _load_page raises RuntimeError on page 1, the category is retried."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_page1_error_then_succeeds(self, mock_load, mock_parse, mock_sleep):
        """First load_page call fails, second succeeds."""
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        call_count = 0

        async def load_page_side_effect(page_obj, url, category, page_num, cooldown_lock=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Spar search broken for obst-gemuese page 1 after 5 retries")

        mock_load.side_effect = load_page_side_effect

        browser, _, _ = _make_mock_browser(tiles_per_call=[3], pagination_text="1 von 1")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 3
        skip_errors = [e for e in error_log if e["type"] == "page_skip" and e["page"] == 1]
        assert len(skip_errors) == 1

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_page1_error_all_retries_fail(self, mock_load, mock_parse, mock_sleep):
        """All category retries fail on page 1 → returns [] and logs category_fail."""
        mock_load.side_effect = RuntimeError("Spar search broken")

        browser, _, _ = _make_mock_browser(tiles_per_call=[])
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert result == []
        fail_errors = [e for e in error_log if e["type"] == "category_fail"]
        assert len(fail_errors) == 1
        assert "broken" in fail_errors[0]["error"].lower()


# ---------------------------------------------------------------------------
# _scrape_category – skip broken pages (page > 1)
# ---------------------------------------------------------------------------

class TestScrapeCategorySkipBrokenPage:
    """When _click_next_page raises an exception, pagination stops and an error is logged."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar._click_next_page", new_callable=AsyncMock)
    async def test_broken_mid_page_skipped(self, mock_click, mock_load, mock_parse, mock_sleep):
        """Page 2 click fails → pagination stops; page 1 products are kept."""
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        async def click_side_effect(page_obj, expected_page):
            if expected_page == 2:
                raise RuntimeError("click failed on page 2")
            return True

        mock_click.side_effect = click_side_effect

        browser, _, _ = _make_mock_browser(tiles_per_call=[3], pagination_text="1 von 3")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 3  # Only page 1 products
        skip_errors = [e for e in error_log if e["type"] == "page_skip"]
        assert len(skip_errors) == 1
        assert skip_errors[0]["page"] == 2

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar._click_next_page", new_callable=AsyncMock)
    async def test_multiple_pages_skipped(self, mock_click, mock_load, mock_parse, mock_sleep):
        """Click failure stops pagination early, logging the error."""
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        async def click_side_effect(page_obj, expected_page):
            if expected_page == 2:
                raise RuntimeError(f"Broken page {expected_page}")
            return True

        mock_click.side_effect = click_side_effect

        browser, _, _ = _make_mock_browser(tiles_per_call=[2], pagination_text="1 von 5")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 2  # Only page 1 products
        skip_errors = [e for e in error_log if e["type"] == "page_skip"]
        assert len(skip_errors) == 1
        assert skip_errors[0]["page"] == 2


# ---------------------------------------------------------------------------
# _scrape_category – normal operation (no errors)
# ---------------------------------------------------------------------------

class TestScrapeCategoryNormal:
    """Verify the happy path still works correctly."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_single_page(self, mock_load, mock_parse, mock_sleep):
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        browser, _, _ = _make_mock_browser(tiles_per_call=[5], pagination_text="1 von 1")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 5
        assert error_log == []

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_multi_page(self, mock_load, mock_parse, mock_sleep):
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        browser, _, _ = _make_mock_browser(tiles_per_call=[3, 3, 2], pagination_text="1 von 3")
        semaphore = asyncio.Semaphore(2)
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", semaphore, error_log)

        assert len(result) == 8
        assert error_log == []

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_no_skipped_pages_no_summary(self, mock_load, mock_parse, mock_sleep):
        """No pages_skipped_summary should be logged when all pages succeed."""
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)
        browser, _, _ = _make_mock_browser(tiles_per_call=[3, 3], pagination_text="1 von 2")
        error_log = []

        result = await _scrape_category(browser, "obst-gemuese", asyncio.Semaphore(2), error_log)

        summaries = [e for e in error_log if e["type"] == "pages_skipped_summary"]
        assert summaries == []


# ---------------------------------------------------------------------------
# _scrape_category – error_log is populated correctly
# ---------------------------------------------------------------------------

class TestScrapeCategoryErrorLog:
    """Verify that error_log entries have the expected shape."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar._click_next_page", new_callable=AsyncMock)
    async def test_page_skip_entry_shape(self, mock_click, mock_load, mock_parse, mock_sleep):
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)

        async def click_fail_page2(page_obj, expected_page):
            if expected_page == 2:
                raise RuntimeError("broken")
            return True

        mock_click.side_effect = click_fail_page2
        browser, _, _ = _make_mock_browser(tiles_per_call=[2], pagination_text="1 von 3")
        error_log = []

        await _scrape_category(browser, "obst-gemuese", asyncio.Semaphore(2), error_log)

        skip = [e for e in error_log if e["type"] == "page_skip"][0]
        assert "category" in skip
        assert "page" in skip
        assert "error" in skip
        assert skip["page"] == 2

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    async def test_empty_page1_retry_entry_shape(self, mock_load, mock_parse, mock_sleep):
        mock_parse.side_effect = lambda tile, cat: _make_product(category=cat)
        browser, _, _ = _make_mock_browser(
            tiles_per_call=[0, 4],
            pagination_text="1 von 1",
        )
        error_log = []

        await _scrape_category(browser, "brot-gebaeck", asyncio.Semaphore(2), error_log)

        retry = [e for e in error_log if e["type"] == "empty_page1_retry"][0]
        assert retry["category"] == "brot-gebaeck"
        assert retry["attempt"] == 1


# ---------------------------------------------------------------------------
# _scrape_spar_async – error log JSON written
# ---------------------------------------------------------------------------

class TestScrapeSparAsyncErrorLog:
    """Verify spar_errors.json is written with the expected structure."""

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar.async_playwright")
    async def test_error_log_json_written(self, mock_pw, mock_load, mock_parse, mock_sleep):
        """Error log JSON is written even when there are no errors."""
        mock_parse.return_value = _make_product()

        # Build a browser mock that returns pages with tiles
        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        pagination = AsyncMock()
        pagination.inner_text = AsyncMock(return_value="1 von 1")
        mock_page.query_selector = AsyncMock(return_value=pagination)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        written_data = {}

        original_open = open

        def capturing_open(path, mode="r", **kwargs):
            if path == ERROR_LOG_FILE and "w" in mode:
                m = mock_open()()
                written_parts = []
                m.write = lambda s: written_parts.append(s)
                written_data["parts"] = written_parts
                return m
            elif "spar.json" in str(path) and "w" in mode:
                return mock_open()()
            return original_open(path, mode, **kwargs)

        with patch("builtins.open", side_effect=capturing_open):
            await _scrape_spar_async()

        # Verify error log was written
        assert "parts" in written_data
        content = "".join(written_data["parts"])
        error_summary = json.loads(content)
        assert "timestamp" in error_summary
        assert "total_errors" in error_summary
        assert "errors" in error_summary
        assert isinstance(error_summary["errors"], list)

    @pytest.mark.asyncio
    @patch("scrapers.spar.asyncio.sleep", new_callable=AsyncMock)
    @patch("scrapers.spar._parse_tile", new_callable=AsyncMock)
    @patch("scrapers.spar._load_page", new_callable=AsyncMock)
    @patch("scrapers.spar.async_playwright")
    async def test_category_exception_logged(self, mock_pw, mock_load, mock_parse, mock_sleep):
        """When gather returns an exception for a category, it's in the error log."""
        mock_parse.return_value = _make_product()

        # Make load_page always raise for one specific category
        async def selective_fail(page_obj, url, category, page_num, cooldown_lock=None):
            if category == "obst-gemuese":
                raise ValueError("Unexpected error in obst-gemuese")

        mock_load.side_effect = selective_fail

        # Mock page that returns tiles for non-failing categories
        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        pagination = AsyncMock()
        pagination.inner_text = AsyncMock(return_value="1 von 1")
        mock_page.query_selector = AsyncMock(return_value=pagination)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        written_data = {}
        original_open = open

        def capturing_open(path, mode="r", **kwargs):
            if path == ERROR_LOG_FILE and "w" in mode:
                m = mock_open()()
                written_parts = []
                m.write = lambda s: written_parts.append(s)
                written_data["parts"] = written_parts
                return m
            elif "spar.json" in str(path) and "w" in mode:
                return mock_open()()
            return original_open(path, mode, **kwargs)

        with (
            patch("builtins.open", side_effect=capturing_open),
            patch("scrapers.spar._take_screenshot", new_callable=AsyncMock),
        ):
            await _scrape_spar_async()

        content = "".join(written_data["parts"])
        error_summary = json.loads(content)
        assert error_summary["total_errors"] > 0
        error_types = [e["type"] for e in error_summary["errors"]]
        assert "category_exception" in error_types
