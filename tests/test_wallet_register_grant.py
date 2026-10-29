"""CSO interim 2026-10-29 (REVISIT #69): registering a bare wallet address grants 0 GCX.

Local only: Firestore is replaced by an in-memory fake; no network.
"""

import pytest

import src.payment.gcx_credits as gcx
from src.mcp_server.server import app


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Doc:
    def __init__(self, store, coll, doc_id):
        self._store, self._coll, self._id = store, coll, doc_id

    def get(self, **_):
        return _Snap(self._store.setdefault(self._coll, {}).get(self._id))

    def set(self, data, merge=False):
        bucket = self._store.setdefault(self._coll, {})
        bucket[self._id] = {**bucket.get(self._id, {}), **data} if merge else dict(data)


class _Coll:
    def __init__(self, store, name):
        self._store, self._name = store, name

    def document(self, doc_id):
        return _Doc(self._store, self._name, doc_id)

    def add(self, data):
        rows = self._store.setdefault(self._name + "#rows", [])
        rows.append(dict(data))
        return None, None


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Coll(self.store, name)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(gcx, "_db", fake)
    return fake


WALLET = "0x" + "ab" * 20  # any 0x + 40 hex string; no signature is asked for


def _credits(db):
    return [r for r in db.store.get("gcx_transactions#rows", []) if r.get("type") == "credit"]


def test_http_register_grants_zero_gcx(db):
    c = app.test_client()
    r = c.post("/api/wallet/register", json={"wallet": WALLET})
    assert r.status_code == 201, r.get_data(as_text=True)[:300]
    assert r.get_json()["balance"] == 0
    assert db.store["gcx_accounts"][WALLET]["balance"] == 0
    assert _credits(db) == []


def test_http_register_via_bearer_header_grants_zero_gcx(db):
    c = app.test_client()
    r = c.post("/api/wallet/register", headers={"Authorization": "Bearer " + WALLET})
    assert r.status_code == 201
    assert db.store["gcx_accounts"][WALLET]["balance"] == 0


def test_mcp_register_wallet_tool_grants_zero_gcx(db):
    from src.tools import _register_wallet

    out = _register_wallet({"wallet": WALLET})
    assert out["status"] == "created"
    assert out["balance"] == 0
    assert db.store["gcx_accounts"][WALLET]["balance"] == 0
    assert _credits(db) == []


def test_existing_account_balance_untouched(db):
    db.store["gcx_accounts"] = {WALLET: {"balance": 42}}
    r = app.test_client().post("/api/wallet/register", json={"wallet": WALLET})
    assert r.status_code == 200
    assert r.get_json()["balance"] == 42
    assert db.store["gcx_accounts"][WALLET]["balance"] == 42


def test_discovery_does_not_advertise_a_free_grant(db):
    c = app.test_client()
    credits = c.get("/api/credits").get_json()
    assert credits["free_trial"]["amount"] == 0
