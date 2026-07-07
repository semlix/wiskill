import pytest
from wiskill.auth import UserStore, Role, _DUMMY_PASSWORD_HASH


def test_add_authenticate_roundtrip(tmp_path):
    us = UserStore(tmp_path / "users.json")
    us.add("alice", "pw123", Role.ADMIN)
    p = us.authenticate("alice", "pw123")
    assert p is not None and p.username == "alice" and p.role == Role.ADMIN
    assert us.authenticate("alice", "bad") is None
    assert us.authenticate("ghost", "pw") is None


def test_duplicate_add_rejected(tmp_path):
    us = UserStore(tmp_path / "users.json")
    us.add("bob", "x", Role.EDITOR)
    with pytest.raises(ValueError):
        us.add("bob", "y", Role.READER)


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "users.json"
    UserStore(path).add("carol", "pw", Role.READER)
    assert UserStore(path).authenticate("carol", "pw").role == Role.READER


def test_set_role_and_remove(tmp_path):
    us = UserStore(tmp_path / "users.json")
    us.add("d", "pw", Role.READER)
    us.set_role("d", Role.EDITOR)
    assert us.authenticate("d", "pw").role == Role.EDITOR
    assert us.remove("d") is True
    assert us.authenticate("d", "pw") is None


def test_dummy_hash_uses_real_cost_params():
    # Regression guard: the unknown-user timing-equalization hash must use
    # the same scrypt cost params as real user hashes (N=16384, r=8, p=1),
    # not a cheap placeholder, or the enumeration timing signal reappears.
    assert _DUMMY_PASSWORD_HASH.startswith("scrypt$16384$8$1$")
