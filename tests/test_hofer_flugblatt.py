import json
from unittest.mock import MagicMock, patch

import pytest

from scrapers import hofer_flugblatt as hf


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey:
    def test_prefers_env_var(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / hf.ANTHROPIC_KEY_FILE).write_text("sk-from-file")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
        assert hf._resolve_api_key() == "sk-from-env"

    def test_falls_back_to_key_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / hf.ANTHROPIC_KEY_FILE).write_text("sk-from-file\n")
        assert hf._resolve_api_key() == "sk-from-file"

    def test_returns_none_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert hf._resolve_api_key() is None

    def test_empty_key_file_is_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / hf.ANTHROPIC_KEY_FILE).write_text("  \n")
        assert hf._resolve_api_key() is None


# ---------------------------------------------------------------------------
# _parse_validity
# ---------------------------------------------------------------------------

class TestParseValidity:
    def test_parses_leaflet_window(self):
        start, end = hf._parse_validity("Flugblatt gültig ab FR. 10.7. bis DO. 16.7.\n")
        assert (start, end) == ("2026-07-10", "2026-07-16")

    def test_ignores_coupon_and_probierpreis_ranges(self):
        # Real page-1 text: the leaflet window is the LAST range, preceded by
        # a product trial-price window and the coupon validity.
        text = (
            "PROBIERPREIS VON 10.7. BIS 6.8.2026\n"
            "Gültig in allen HOFER Filialen von 29.6. bis 19.7.2026\n"
            "Flugblatt gültig ab FR. 10.7. bis DO. 16.7.\n"
        )
        assert hf._parse_validity(text) == ("2026-07-10", "2026-07-16")

    def test_ignores_section_header_range(self):
        # KW28: the "WOCHEN-START" header (MO. 6.7. BIS DO. 9.7.) is not the
        # leaflet window, which actually starts on 3.7.
        text = "MO. 6.7. BIS DO. 9.7.\nFlugblatt gültig ab FR. 3.7. bis DO. 9.7.\n"
        assert hf._parse_validity(text) == ("2026-07-03", "2026-07-09")

    def test_handles_spaces_inside_dates(self):
        start, end = hf._parse_validity("Flugblatt gültig ab MO. 6 . 7. bis DO.\xa09. 7.")
        assert (start, end) == ("2026-07-06", "2026-07-09")

    def test_handles_year_rollover(self):
        start, end = hf._parse_validity("Flugblatt gültig ab FR. 27.12. bis DO. 2.1.")
        assert start == "2026-12-27"
        assert end == "2027-01-02"

    def test_returns_none_when_absent(self):
        assert hf._parse_validity("kein Datum hier") == (None, None)

    def test_returns_none_without_anchor_phrase(self):
        # A bare date range must NOT be treated as the leaflet window.
        assert hf._parse_validity("MO. 6.7. BIS DO. 9.7.") == (None, None)

    def test_returns_none_on_invalid_date(self):
        assert hf._parse_validity("Flugblatt gültig ab MO. 6.13. bis DO. 9.13.") == (None, None)


# ---------------------------------------------------------------------------
# _build_product
# ---------------------------------------------------------------------------

class TestBuildProduct:
    def _raw(self, **over):
        base = {
            "name": "Emmentaler Scheiben", "brand": "Milsani", "price": 4.99,
            "originalPrice": 7.49, "amount": "250 g", "unitPrice": 19.96,
            "unitLabel": "kg", "promotionText": "-33%",
        }
        base.update(over)
        return base

    def test_full_product(self):
        p = hf._build_product(self._raw(), "2026-07-06", "2026-07-09")
        assert p["id"].startswith("hofer_fb_")
        assert p["name"] == "Emmentaler Scheiben"
        assert p["price"] == 4.99
        assert p["originalPrice"] == 7.49
        assert p["unitPrice"] == 19.96
        assert p["brand"] == "Milsani"
        assert p["amount"] == "250 g"
        assert p["inPromotion"] is True
        assert p["supermarket"] == "hofer"
        assert p["sku"] is None
        assert p["offerStart"] == "2026-07-06"
        assert p["nameTokens"] == ["emmentaler", "scheiben"]

    def test_stable_id_across_calls(self):
        a = hf._build_product(self._raw(), None, None)
        b = hf._build_product(self._raw(), "2026-07-06", "2026-07-09")
        # id depends on brand+name+amount, not on the offer window
        assert a["id"] == b["id"]

    def test_id_differs_by_amount(self):
        a = hf._build_product(self._raw(amount="250 g"), None, None)
        b = hf._build_product(self._raw(amount="500 g"), None, None)
        assert a["id"] != b["id"]

    def test_missing_price_returns_none(self):
        assert hf._build_product(self._raw(price=None), None, None) is None

    def test_missing_name_returns_none(self):
        assert hf._build_product(self._raw(name=""), None, None) is None

    def test_null_optional_fields(self):
        p = hf._build_product(
            {"name": "Brot", "price": 1.99, "brand": None, "originalPrice": None,
             "amount": None, "unitPrice": None, "unitLabel": None, "promotionText": None},
            None, None,
        )
        assert p["originalPrice"] is None
        assert p["unitPrice"] is None
        assert p["brand"] is None


# ---------------------------------------------------------------------------
# _dedupe
# ---------------------------------------------------------------------------

def test_dedupe_drops_repeated_ids():
    products = [
        {"id": "hofer_fb_1", "name": "A"},
        {"id": "hofer_fb_1", "name": "A again"},
        {"id": "hofer_fb_2", "name": "B"},
    ]
    unique = hf._dedupe(products)
    assert [p["id"] for p in unique] == ["hofer_fb_1", "hofer_fb_2"]


# ---------------------------------------------------------------------------
# _extract_page (mocked Claude client)
# ---------------------------------------------------------------------------

class TestExtractPage:
    def _client(self, payload):
        client = MagicMock()
        resp = MagicMock()
        block = MagicMock()
        block.type = "text"
        block.text = json.dumps(payload)
        resp.content = [block]
        client.messages.create.return_value = resp
        return client

    def test_parses_products(self):
        client = self._client({"products": [{"name": "Milka", "price": 1.99}]})
        items = hf._extract_page(client, b"png")
        assert items == [{"name": "Milka", "price": 1.99}]

    def test_uses_vision_and_schema(self):
        client = self._client({"products": []})
        hf._extract_page(client, b"png")
        kw = client.messages.create.call_args.kwargs
        assert kw["model"] == hf.MODEL
        assert kw["messages"][0]["content"][0]["type"] == "image"
        assert kw["output_config"]["format"]["type"] == "json_schema"

    def test_empty_text_returns_empty(self):
        client = MagicMock()
        resp = MagicMock()
        resp.content = []
        client.messages.create.return_value = resp
        assert hf._extract_page(client, b"png") == []


# ---------------------------------------------------------------------------
# scrape_hofer_flugblatt (mocked discovery / cache / key)
# ---------------------------------------------------------------------------

class TestScrapeHoferFlugblatt:
    @patch("scrapers.hofer_flugblatt._discover_flugblatt")
    def test_uses_cache_without_calling_llm(self, mock_discover, tmp_path, monkeypatch):
        monkeypatch.setattr(hf, "CACHE_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        mock_discover.return_value = ("flipbook_kw28_26_2", "https://x/y.pdf")
        cached = [{"id": "hofer_fb_1", "name": "Cached"}]
        hf._save_cache("flipbook_kw28_26_2", cached)

        with patch("scrapers.hofer_flugblatt._extract_flugblatt") as mock_extract:
            products = hf.scrape_hofer_flugblatt()
            mock_extract.assert_not_called()
        assert products == cached

    @patch("scrapers.hofer_flugblatt._discover_flugblatt")
    def test_skips_without_api_key(self, mock_discover, tmp_path, monkeypatch):
        monkeypatch.setattr(hf, "CACHE_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_discover.return_value = ("flipbook_new", "https://x/y.pdf")

        products = hf.scrape_hofer_flugblatt()
        assert products == []

    @patch("scrapers.hofer_flugblatt._discover_flugblatt")
    def test_no_leaflet_found(self, mock_discover, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_discover.return_value = (None, None)
        products = hf.scrape_hofer_flugblatt()
        assert products == []

    @patch("scrapers.hofer_flugblatt.requests.get")
    @patch("scrapers.hofer_flugblatt._extract_flugblatt")
    @patch("scrapers.hofer_flugblatt._discover_flugblatt")
    def test_caches_successful_extraction(self, mock_discover, mock_extract, mock_get, tmp_path, monkeypatch):
        monkeypatch.setattr(hf, "CACHE_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        mock_discover.return_value = ("flipbook_new", "https://x/y.pdf")
        mock_get.return_value = MagicMock(content=b"%PDF")
        mock_extract.return_value = [{"id": "hofer_fb_1", "name": "Milch"}]

        products = hf.scrape_hofer_flugblatt()
        assert len(products) == 1
        # cache was written so a second run reuses it without extracting again
        assert hf._load_cache("flipbook_new") == [{"id": "hofer_fb_1", "name": "Milch"}]

    @patch("scrapers.hofer_flugblatt.requests.get")
    @patch("scrapers.hofer_flugblatt._extract_flugblatt")
    @patch("scrapers.hofer_flugblatt._discover_flugblatt")
    def test_does_not_cache_empty_extraction(self, mock_discover, mock_extract, mock_get, tmp_path, monkeypatch):
        monkeypatch.setattr(hf, "CACHE_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        mock_discover.return_value = ("flipbook_new", "https://x/y.pdf")
        mock_get.return_value = MagicMock(content=b"%PDF")
        mock_extract.return_value = []  # transient failure

        products = hf.scrape_hofer_flugblatt()
        assert products == []
        # nothing cached → a later run will retry instead of returning 0 forever
        assert hf._load_cache("flipbook_new") is None
