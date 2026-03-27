"""Integration: --upload-only mode with real JSON files on disk.

Tests write known JSON files, run ``main()`` with ``--upload-only``,
and verify that the correct products are forwarded to ``upload_all``.
"""

import json
import pytest
from unittest.mock import patch

from tests.integration.helpers import make_product

pytestmark = pytest.mark.integration


PRODUCTS_BILLA = [
    make_product("billa", "00-100001", "Bio Milch", 1.39),
    make_product("billa", "00-100002", "Butter", 2.99),
]

PRODUCTS_SPAR = [
    make_product("spar", "2020005521308", "Bio Apfel", 2.99),
]


class TestUploadOnlyMode:
    @patch("main.upload_all")
    def test_reads_and_uploads_json_files(self, mock_upload, tmp_workdir):
        # Write realistic JSON files
        (tmp_workdir / "billa.json").write_text(
            json.dumps(PRODUCTS_BILLA, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (tmp_workdir / "spar.json").write_text(
            json.dumps(PRODUCTS_SPAR, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        scrapers = {
            "billa": ("billa.json", None),
            "spar":  ("spar.json",  None),
        }

        with patch("main.SCRAPERS", scrapers):
            with patch("sys.argv", ["main.py", "--upload-only"]):
                import main
                main.main()

        mock_upload.assert_called_once()
        arg = mock_upload.call_args[0][0]
        assert set(arg.keys()) == {"billa", "spar"}
        assert arg["billa"] == PRODUCTS_BILLA
        assert arg["spar"] == PRODUCTS_SPAR

    @patch("main.upload_all")
    def test_missing_file_is_skipped(self, mock_upload, tmp_workdir):
        # Only write one file — the other is intentionally missing
        (tmp_workdir / "billa.json").write_text(
            json.dumps(PRODUCTS_BILLA, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        scrapers = {
            "billa": ("billa.json", None),
            "spar":  ("spar.json",  None),
        }

        with patch("main.SCRAPERS", scrapers):
            with patch("sys.argv", ["main.py", "--upload-only"]):
                import main
                main.main()

        mock_upload.assert_called_once()
        arg = mock_upload.call_args[0][0]
        # Only billa was loaded; spar was skipped with a warning
        assert "billa" in arg
        assert "spar" not in arg
        assert arg["billa"] == PRODUCTS_BILLA

    @patch("main.upload_all")
    def test_empty_json_file(self, mock_upload, tmp_workdir):
        """An empty product list in a JSON file is loaded and forwarded."""
        (tmp_workdir / "billa.json").write_text("[]", encoding="utf-8")

        scrapers = {
            "billa": ("billa.json", None),
        }

        with patch("main.SCRAPERS", scrapers):
            with patch("sys.argv", ["main.py", "--upload-only"]):
                import main
                main.main()

        mock_upload.assert_called_once()
        arg = mock_upload.call_args[0][0]
        assert arg["billa"] == []
