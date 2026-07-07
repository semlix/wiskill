"""Auth: roles, principals, password hashing, user + API-key stores."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1


class Role(str, Enum):
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {"reader": 0, "editor": 1, "admin": 2}[self.value]

    def allows(self, needed: "Role") -> bool:
        return self.rank >= needed.rank


@dataclass
class Principal:
    username: str
    role: Role


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(dk, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


# Precomputed once at import time using the *real* scrypt cost params, so the
# unknown-user branch of UserStore.authenticate takes the same time as a real
# verify — closing the user-enumeration timing side channel.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(16))


class UserStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"users": {}}

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, username: str, password: str, role: Role) -> None:
        data = self._load()
        if username in data["users"]:
            raise ValueError(f"user exists: {username}")
        data["users"][username] = {"hash": hash_password(password), "role": role.value}
        self._save(data)

    def set_password(self, username: str, password: str) -> None:
        data = self._load()
        if username not in data["users"]:
            raise ValueError(f"no such user: {username}")
        data["users"][username]["hash"] = hash_password(password)
        self._save(data)

    def set_role(self, username: str, role: Role) -> None:
        data = self._load()
        if username not in data["users"]:
            raise ValueError(f"no such user: {username}")
        data["users"][username]["role"] = role.value
        self._save(data)

    def remove(self, username: str) -> bool:
        data = self._load()
        if username not in data["users"]:
            return False
        del data["users"][username]
        self._save(data)
        return True

    def list_users(self) -> list[tuple[str, Role]]:
        data = self._load()
        return sorted((u, Role(rec["role"])) for u, rec in data["users"].items())

    def authenticate(self, username: str, password: str) -> Principal | None:
        data = self._load()
        rec = data["users"].get(username)
        if rec is None:
            # Hash anyway to reduce user-enumeration timing signal.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            return None
        if verify_password(password, rec["hash"]):
            return Principal(username=username, role=Role(rec["role"]))
        return None
