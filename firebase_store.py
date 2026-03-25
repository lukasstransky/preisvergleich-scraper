"""Firebase Firestore integration.

Uses diff-based sync (see ``firestore_sync.py``) with per-supermarket
collections to minimise daily read/write quota usage.
"""

import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

from firestore_sync import sync_products


def _collection_name(supermarket: str) -> str:
    """Map supermarket key to its Firestore collection name."""
    return f"{supermarket}_products"


def init_firebase():
    """Initialize Firebase Admin SDK.

    Credentials are resolved in this order:
    1. FIREBASE_KEY env var containing the service-account JSON string.
    2. A local ``firebase-key.json`` file.

    Returns the Firestore client, or None if credentials are unavailable.
    """
    if firebase_admin._apps:
        return firestore.client()

    key_json = os.environ.get("FIREBASE_KEY")
    if key_json:
        cred = credentials.Certificate(json.loads(key_json))
    elif os.path.exists("firebase-key.json"):
        cred = credentials.Certificate("firebase-key.json")
    else:
        print("WARNING: No Firebase credentials found. Skipping upload.")
        print("  Set FIREBASE_KEY env var or place firebase-key.json in project root.")
        return None

    firebase_admin.initialize_app(cred)
    return firestore.client()


def upload_products(db, products, supermarket):
    """Sync a list of product dicts to Firestore using diff-based updates.

    Only writes new/changed products and deletes removed ones.
    Each supermarket has its own collection (e.g. ``penny_products``).
    """
    if not db:
        return

    collection = _collection_name(supermarket)
    sync_products(db, products, collection)


def upload_all(products_by_supermarket):
    """Initialize Firebase and sync products for all supermarkets.

    Args:
        products_by_supermarket: dict mapping supermarket name to product list,
            e.g. {"billa": [...], "spar": [...], "hofer": [...], "penny": [...]}.
    """
    db = init_firebase()
    if not db:
        return

    total_ops = 0
    for supermarket, products in products_by_supermarket.items():
        print(f"Syncing {supermarket} ({len(products)} products)…")
        upload_products(db, products, supermarket)
        print()

    print("Firebase sync complete.")
