"""Tests for firebase_store.py – Firebase init and per-supermarket sync."""

import json
import os
from unittest.mock import MagicMock, patch, call

import pytest

from firebase_store import (
    _collection_name,
    init_firebase,
    upload_products,
    upload_all,
)


# ---------------------------------------------------------------------------
# _collection_name
# ---------------------------------------------------------------------------

class TestCollectionName:
    def test_penny(self):
        assert _collection_name("penny") == "penny_products"

    def test_billa(self):
        assert _collection_name("billa") == "billa_products"

    def test_hofer(self):
        assert _collection_name("hofer") == "hofer_products"

    def test_spar(self):
        assert _collection_name("spar") == "spar_products"


# ---------------------------------------------------------------------------
# init_firebase
# ---------------------------------------------------------------------------

class TestInitFirebase:
    @patch("firebase_store.firebase_admin")
    @patch("firebase_store.firestore")
    def test_returns_existing_client_if_already_initialized(self, mock_fs, mock_admin):
        mock_admin._apps = {"default": True}
        mock_fs.client.return_value = MagicMock()

        db = init_firebase()

        assert db is not None
        mock_fs.client.assert_called_once()
        mock_admin.initialize_app.assert_not_called()

    @patch("firebase_store.firebase_admin")
    @patch("firebase_store.firestore")
    @patch("firebase_store.credentials")
    @patch.dict(os.environ, {"FIREBASE_KEY": '{"type": "service_account"}'})
    def test_initializes_from_env_var(self, mock_creds, mock_fs, mock_admin):
        mock_admin._apps = {}
        mock_fs.client.return_value = MagicMock()

        db = init_firebase()

        assert db is not None
        mock_creds.Certificate.assert_called_once_with({"type": "service_account"})
        mock_admin.initialize_app.assert_called_once()

    @patch("firebase_store.firebase_admin")
    @patch("firebase_store.firestore")
    @patch("firebase_store.credentials")
    @patch("firebase_store.os.path.exists", return_value=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_initializes_from_json_file(self, mock_exists, mock_creds, mock_fs, mock_admin):
        mock_admin._apps = {}
        mock_fs.client.return_value = MagicMock()

        db = init_firebase()

        assert db is not None
        mock_creds.Certificate.assert_called_once_with("firebase-key.json")
        mock_admin.initialize_app.assert_called_once()

    @patch("firebase_store.firebase_admin")
    @patch("firebase_store.os.path.exists", return_value=False)
    @patch.dict(os.environ, {}, clear=True)
    def test_returns_none_when_no_credentials(self, mock_exists, mock_admin, capsys):
        mock_admin._apps = {}

        db = init_firebase()

        assert db is None
        output = capsys.readouterr().out
        assert "WARNING" in output


# ---------------------------------------------------------------------------
# upload_products
# ---------------------------------------------------------------------------

class TestUploadProducts:
    @patch("firebase_store.sync_products")
    def test_calls_sync_with_correct_collection(self, mock_sync):
        db = MagicMock()
        products = [{"id": "p1", "name": "Test"}]

        upload_products(db, products, "penny")

        mock_sync.assert_called_once_with(db, products, "penny_products")

    @patch("firebase_store.sync_products")
    def test_skips_when_db_is_none(self, mock_sync):
        upload_products(None, [{"id": "p1"}], "billa")
        mock_sync.assert_not_called()

    @patch("firebase_store.sync_products")
    def test_each_supermarket_gets_own_collection(self, mock_sync):
        db = MagicMock()
        for sm in ["billa", "spar", "hofer", "penny"]:
            upload_products(db, [{"id": f"{sm}_1"}], sm)

        calls = mock_sync.call_args_list
        collections_used = [c.args[2] for c in calls]
        assert collections_used == [
            "billa_products",
            "spar_products",
            "hofer_products",
            "penny_products",
        ]


# ---------------------------------------------------------------------------
# upload_all
# ---------------------------------------------------------------------------

class TestUploadAll:
    @patch("firebase_store.upload_products")
    @patch("firebase_store.init_firebase")
    def test_syncs_all_supermarkets(self, mock_init, mock_upload):
        mock_db = MagicMock()
        mock_init.return_value = mock_db

        products_map = {
            "billa": [{"id": "b1"}],
            "penny": [{"id": "p1"}, {"id": "p2"}],
        }
        upload_all(products_map)

        assert mock_upload.call_count == 2
        mock_upload.assert_any_call(mock_db, [{"id": "b1"}], "billa")
        mock_upload.assert_any_call(mock_db, [{"id": "p1"}, {"id": "p2"}], "penny")

    @patch("firebase_store.upload_products")
    @patch("firebase_store.init_firebase")
    def test_skips_when_no_firebase(self, mock_init, mock_upload):
        mock_init.return_value = None

        upload_all({"penny": [{"id": "p1"}]})

        mock_upload.assert_not_called()

    @patch("firebase_store.upload_products")
    @patch("firebase_store.init_firebase")
    def test_prints_completion_message(self, mock_init, mock_upload, capsys):
        mock_init.return_value = MagicMock()

        upload_all({"penny": []})

        output = capsys.readouterr().out
        assert "Firebase sync complete" in output

    @patch("firebase_store.upload_products")
    @patch("firebase_store.init_firebase")
    def test_handles_empty_dict(self, mock_init, mock_upload, capsys):
        mock_init.return_value = MagicMock()

        upload_all({})

        mock_upload.assert_not_called()
        output = capsys.readouterr().out
        assert "Firebase sync complete" in output

    @patch("firebase_store.upload_products")
    @patch("firebase_store.init_firebase")
    def test_prints_request_summary(self, mock_init, mock_upload, capsys):
        mock_init.return_value = MagicMock()

        upload_all({"penny": [{"id": "p1"}]})

        output = capsys.readouterr().out
        assert "Firestore request summary" in output
        assert "Reads" in output
        assert "Writes" in output
        assert "Deletes" in output
        assert "Total" in output
