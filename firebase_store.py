import json
import os

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

PRODUCTS_COLLECTION = "products"
BATCH_SIZE = 500


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


def _delete_collection(db, supermarket):
    """Delete all documents for a given supermarket from the products collection."""
    docs = (
        db.collection(PRODUCTS_COLLECTION)
        .where(filter=FieldFilter("supermarket", "==", supermarket))
        .stream()
    )

    batch = db.batch()
    count = 0

    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count % BATCH_SIZE == 0:
            batch.commit()
            batch = db.batch()

    if count % BATCH_SIZE != 0:
        batch.commit()

    return count


def upload_products(db, products, supermarket):
    """Upload a list of product dicts to Firestore.

    1. Deletes all existing documents for the supermarket.
    2. Writes all new products in batches.
    """
    if not db:
        return

    if not products:
        print(f"  No products to upload for {supermarket}")
        return

    # Delete stale products
    deleted = _delete_collection(db, supermarket)
    print(f"  Deleted {deleted} old {supermarket} documents")

    # Batch write new products
    batch = db.batch()
    count = 0

    for product in products:
        doc_id = product.get("id")
        if not doc_id:
            continue

        doc_ref = db.collection(PRODUCTS_COLLECTION).document(doc_id)
        batch.set(doc_ref, product)
        count += 1

        if count % BATCH_SIZE == 0:
            batch.commit()
            batch = db.batch()
            print(f"  Committed {count}/{len(products)} {supermarket} products...")

    if count % BATCH_SIZE != 0:
        batch.commit()

    print(f"  Uploaded {count} {supermarket} products to Firestore")


def upload_all(products_by_supermarket):
    """Initialize Firebase and upload products for all supermarkets.

    Args:
        products_by_supermarket: dict mapping supermarket name to product list,
            e.g. {"billa": [...], "spar": [...], "hofer": [...], "penny": [...]}.
    """
    db = init_firebase()
    if not db:
        return

    for supermarket, products in products_by_supermarket.items():
        print(f"Uploading {supermarket} ({len(products)} products)...")
        upload_products(db, products, supermarket)

    print("Firebase upload complete.")
