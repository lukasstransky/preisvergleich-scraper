"""In-memory Firestore fake for integration tests.

Implements the subset of the Firestore client API used by ``firestore_sync.py``:
``db.collection(...).document(...).get()``, ``db.batch()``,
``batch.set(ref, data)``, ``batch.delete(ref)``, ``batch.commit()``,
and ``doc_ref.set(data)``.
"""


class FakeDocumentSnapshot:
    """Mimics ``google.cloud.firestore.DocumentSnapshot``."""

    def __init__(self, data, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class FakeDocumentReference:
    """Mimics ``google.cloud.firestore.DocumentReference``."""

    def __init__(self, collection, doc_id):
        self._collection = collection
        self._doc_id = doc_id

    @property
    def id(self):
        return self._doc_id

    def get(self):
        data = self._collection._docs.get(self._doc_id)
        if data is None:
            return FakeDocumentSnapshot(None, exists=False)
        return FakeDocumentSnapshot(data)

    def set(self, data):
        self._collection._docs[self._doc_id] = data

    def __repr__(self):
        return f"FakeDocumentReference({self._collection._name!r}, {self._doc_id!r})"


class FakeCollection:
    """Mimics ``google.cloud.firestore.CollectionReference``."""

    def __init__(self, name):
        self._name = name
        self._docs: dict[str, dict] = {}

    def document(self, doc_id):
        return FakeDocumentReference(self, doc_id)


class FakeBatch:
    """Mimics ``google.cloud.firestore.WriteBatch``."""

    def __init__(self):
        self._ops: list[tuple] = []

    def set(self, ref: FakeDocumentReference, data: dict):
        self._ops.append(("set", ref, data))

    def delete(self, ref: FakeDocumentReference):
        self._ops.append(("delete", ref, None))

    def commit(self):
        for op, ref, data in self._ops:
            if op == "set":
                ref.set(data)
            elif op == "delete":
                ref._collection._docs.pop(ref._doc_id, None)
        self._ops.clear()


class FakeFirestoreDB:
    """In-memory Firestore client for integration tests.

    Usage::

        db = FakeFirestoreDB()
        # optionally pre-populate:
        db.collection("_sync_metadata").document("billa_products").set(
            {"hashes": {"billa_123": "abc..."}}
        )
    """

    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def collection(self, name) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection(name)
        return self._collections[name]

    def batch(self) -> FakeBatch:
        return FakeBatch()

    # ── helpers for assertions ───────────────────────────────────────────

    def get_all_docs(self, collection_name: str) -> dict[str, dict]:
        """Return all documents in a collection as {doc_id: data}."""
        col = self._collections.get(collection_name)
        if col is None:
            return {}
        return dict(col._docs)

    def doc_exists(self, collection_name: str, doc_id: str) -> bool:
        col = self._collections.get(collection_name)
        return col is not None and doc_id in col._docs
