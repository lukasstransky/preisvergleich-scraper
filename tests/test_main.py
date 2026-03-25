"""Tests for main.py – CLI entry point."""

import json
import os
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from main import _fmt_duration, _load_from_json, main


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_below_one_minute(self):
        assert _fmt_duration(0) == "0.0s"

    def test_seconds(self):
        assert _fmt_duration(5.5) == "5.5s"

    def test_exactly_60_seconds(self):
        assert _fmt_duration(60) == "1.0m"

    def test_above_one_minute(self):
        assert _fmt_duration(90) == "1.5m"

    def test_two_minutes(self):
        assert _fmt_duration(120) == "2.0m"

    def test_just_below_60(self):
        assert _fmt_duration(59.9) == "59.9s"


# ---------------------------------------------------------------------------
# _load_from_json
# ---------------------------------------------------------------------------

class TestLoadFromJson:
    def test_returns_parsed_products(self, tmp_path):
        products = [{"id": "billa_1", "name": "Apfel"}, {"id": "billa_2", "name": "Birne"}]
        json_file = tmp_path / "billa.json"
        json_file.write_text(json.dumps(products), encoding="utf-8")

        result = _load_from_json(str(json_file))

        assert result == products

    def test_prints_count(self, tmp_path, capsys):
        products = [{"id": "x_1"}]
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(products), encoding="utf-8")

        _load_from_json(str(json_file))

        captured = capsys.readouterr()
        assert "1" in captured.out

    def test_empty_file(self, tmp_path):
        json_file = tmp_path / "empty.json"
        json_file.write_text("[]", encoding="utf-8")

        result = _load_from_json(str(json_file))

        assert result == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_from_json(str(tmp_path / "nonexistent.json"))


# ---------------------------------------------------------------------------
# main() – upload-only mode
# ---------------------------------------------------------------------------

FAKE_PRODUCTS = [{"id": "x_1", "name": "Test"}]

# SCRAPERS holds direct function references captured at import time, so we must
# patch main.SCRAPERS itself rather than patching the individual function names.
FAKE_SCRAPERS = {
    "billa": ("billa.json", MagicMock(return_value=FAKE_PRODUCTS)),
    "spar":  ("spar.json",  MagicMock(return_value=FAKE_PRODUCTS)),
    "hofer": ("hofer.json", MagicMock(return_value=FAKE_PRODUCTS)),
    "penny": ("penny.json", MagicMock(return_value=FAKE_PRODUCTS)),
}


def _fresh_scrapers():
    """Return a new SCRAPERS dict with fresh MagicMocks (so call counts start at 0)."""
    return {
        name: (json_file, MagicMock(return_value=FAKE_PRODUCTS))
        for name, (json_file, _) in FAKE_SCRAPERS.items()
    }


# ---------------------------------------------------------------------------
# main() – upload-only mode
# ---------------------------------------------------------------------------

class TestMainUploadOnly:
    @patch("main.upload_all")
    @patch("main.os.path.exists", return_value=True)
    @patch("main._load_from_json", return_value=FAKE_PRODUCTS)
    def test_loads_all_scrapers_from_json(self, mock_load, mock_exists, mock_upload):
        with patch("sys.argv", ["main.py", "--upload-only"]):
            main()

        assert mock_load.call_count == 4  # billa, spar, hofer, penny

    @patch("main.upload_all")
    @patch("main.os.path.exists", return_value=True)
    @patch("main._load_from_json", return_value=FAKE_PRODUCTS)
    def test_calls_upload_all_with_all_products(self, mock_load, mock_exists, mock_upload):
        with patch("sys.argv", ["main.py", "--upload-only"]):
            main()

        mock_upload.assert_called_once()
        uploaded = mock_upload.call_args[0][0]
        assert set(uploaded.keys()) == {"billa", "spar", "hofer", "penny"}

    @patch("main.upload_all")
    @patch("main.os.path.exists", return_value=False)
    @patch("main._load_from_json")
    def test_skips_missing_json_files(self, mock_load, mock_exists, mock_upload):
        with patch("sys.argv", ["main.py", "--upload-only"]):
            main()

        mock_load.assert_not_called()

    @patch("main.upload_all")
    @patch("main.os.path.exists", return_value=False)
    def test_warns_about_missing_files(self, mock_exists, mock_upload, capsys):
        with patch("sys.argv", ["main.py", "--upload-only"]):
            main()

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    @patch("main.upload_all")
    @patch("main.os.path.exists", return_value=True)
    @patch("main._load_from_json", return_value=FAKE_PRODUCTS)
    def test_does_not_call_scrapers(self, mock_load, mock_exists, mock_upload):
        scrapers = _fresh_scrapers()
        with patch("main.SCRAPERS", scrapers), patch("sys.argv", ["main.py", "--upload-only"]):
            main()

        for _, scrape_fn in scrapers.values():
            scrape_fn.assert_not_called()


# ---------------------------------------------------------------------------
# main() – no-upload mode
# ---------------------------------------------------------------------------

class TestMainNoUpload:
    def test_does_not_call_upload(self):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all") as mock_upload,
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py", "--no-upload"]),
        ):
            main()

        mock_upload.assert_not_called()

    def test_calls_all_scrapers(self):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all"),
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py", "--no-upload"]),
        ):
            main()

        for _, scrape_fn in scrapers.values():
            scrape_fn.assert_called_once()

    def test_prints_skipping_upload_message(self, capsys):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all"),
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py", "--no-upload"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "--no-upload" in captured.out


# ---------------------------------------------------------------------------
# main() – normal mode (scrape + upload)
# ---------------------------------------------------------------------------

class TestMainNormalMode:
    def test_calls_all_scrapers_and_upload(self):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all") as mock_upload,
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py"]),
        ):
            main()

        for _, scrape_fn in scrapers.values():
            scrape_fn.assert_called_once()
        mock_upload.assert_called_once()

    def test_deletes_existing_json_files_before_scraping(self):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all"),
            patch("main.os.remove") as mock_remove,
            patch("main.os.path.exists", return_value=True),
            patch("sys.argv", ["main.py"]),
        ):
            main()

        assert mock_remove.call_count == 4
        removed_files = {c.args[0] for c in mock_remove.call_args_list}
        assert removed_files == {"billa.json", "spar.json", "hofer.json", "penny.json"}

    def test_upload_receives_all_scraped_products(self):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all") as mock_upload,
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py"]),
        ):
            main()

        uploaded = mock_upload.call_args[0][0]
        assert set(uploaded.keys()) == {"billa", "spar", "hofer", "penny"}
        assert uploaded["billa"] == FAKE_PRODUCTS

    def test_prints_timing_summary(self, capsys):
        scrapers = _fresh_scrapers()
        with (
            patch("main.SCRAPERS", scrapers),
            patch("main.upload_all"),
            patch("main.os.remove"),
            patch("main.os.path.exists", return_value=False),
            patch("sys.argv", ["main.py"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "Timing summary" in captured.out
        assert "Total" in captured.out
