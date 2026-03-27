"""Integration: main.py orchestration flow.

Tests exercise the real ``main()`` function with fake scrapers that
write actual JSON files, verifying the end-to-end flow without
touching real HTTP, browsers, or Firebase.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import REQUIRED_PRODUCT_KEYS, OPTIONAL_PRODUCT_KEYS
from tests.integration.helpers import make_product

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────────────────
# Fake scraper helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_fake_scraper(json_file, supermarket, products):
    """Return a scrape function that writes products to *json_file* and returns them."""

    def scrape():
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        return products

    return scrape


FAKE_PRODUCTS_A = [
    make_product("alpha", "A001", "Milch", 1.39),
    make_product("alpha", "A002", "Butter", 2.99),
]

FAKE_PRODUCTS_B = [
    make_product("beta", "B001", "Brot", 2.49),
]


def _fresh_scrapers():
    """Build a SCRAPERS dict with two fake scrapers."""
    return {
        "alpha": ("alpha.json", _make_fake_scraper("alpha.json", "alpha", FAKE_PRODUCTS_A)),
        "beta":  ("beta.json",  _make_fake_scraper("beta.json", "beta", FAKE_PRODUCTS_B)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Normal mode
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalMode:
    @patch("main.upload_all")
    def test_scrape_and_upload(self, mock_upload, tmp_workdir):
        with patch("main.SCRAPERS", _fresh_scrapers()):
            with patch("sys.argv", ["main.py"]):
                import main
                main.main()

        # JSON files were written
        assert (tmp_workdir / "alpha.json").exists()
        assert (tmp_workdir / "beta.json").exists()

        # upload_all was called with the right data
        mock_upload.assert_called_once()
        arg = mock_upload.call_args[0][0]
        assert set(arg.keys()) == {"alpha", "beta"}
        assert len(arg["alpha"]) == 2
        assert len(arg["beta"]) == 1

    @patch("main.upload_all")
    def test_old_json_files_are_deleted(self, mock_upload, tmp_workdir):
        # Pre-create stale JSON files
        (tmp_workdir / "alpha.json").write_text("[]")
        (tmp_workdir / "beta.json").write_text("[]")

        with patch("main.SCRAPERS", _fresh_scrapers()):
            with patch("sys.argv", ["main.py"]):
                import main
                main.main()

        # Files now contain the fresh data (not empty)
        with open(tmp_workdir / "alpha.json") as f:
            data = json.load(f)
        assert len(data) == 2


# ──────────────────────────────────────────────────────────────────────────────
# --no-upload mode
# ──────────────────────────────────────────────────────────────────────────────

class TestNoUploadMode:
    @patch("main.upload_all")
    def test_no_upload_skips_firebase(self, mock_upload, tmp_workdir):
        with patch("main.SCRAPERS", _fresh_scrapers()):
            with patch("sys.argv", ["main.py", "--no-upload"]):
                import main
                main.main()

        mock_upload.assert_not_called()

        # But JSON files were still written
        assert (tmp_workdir / "alpha.json").exists()
        assert (tmp_workdir / "beta.json").exists()


# ──────────────────────────────────────────────────────────────────────────────
# Error resilience
# ──────────────────────────────────────────────────────────────────────────────

class TestErrorResilience:
    @patch("main.upload_all")
    def test_one_scraper_failure_propagates(self, mock_upload, tmp_workdir):
        """main.py does not catch scraper exceptions — they propagate and stop the run."""

        def failing_scraper():
            raise RuntimeError("Network error")

        scrapers = {
            "alpha": ("alpha.json", _make_fake_scraper("alpha.json", "alpha", FAKE_PRODUCTS_A)),
            "broken": ("broken.json", failing_scraper),
        }

        with patch("main.SCRAPERS", scrapers):
            with patch("sys.argv", ["main.py", "--no-upload"]):
                import main
                with pytest.raises(RuntimeError, match="Network error"):
                    main.main()

        # The scraper that ran before the broken one still wrote its file
        assert (tmp_workdir / "alpha.json").exists()
        # The broken scraper did not write a file
        assert not (tmp_workdir / "broken.json").exists()
