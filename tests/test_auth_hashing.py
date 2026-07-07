from wiskill.auth import Role, hash_password, verify_password


def test_role_ordering():
    assert Role.ADMIN.allows(Role.EDITOR)
    assert Role.EDITOR.allows(Role.READER)
    assert not Role.READER.allows(Role.EDITOR)


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h.startswith("scrypt$")
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)


def test_hash_is_salted():
    assert hash_password("x") != hash_password("x")


def test_verify_password_rejects_malformed_stored_without_raising():
    valid = hash_password("s3cret")
    _, n, r, p, salt_hex, hash_hex = valid.split("$")

    # Exact crash case: non-ASCII byte in the hash field breaks
    # hmac.compare_digest on hex strings (TypeError) unless compared as bytes.
    non_ascii_hash = "scrypt$" + n + "$" + r + "$" + p + "$" + salt_hex + "$" + "é" * len(hash_hex)
    assert verify_password("s3cret", non_ascii_hash) is False

    # Wrong field count.
    assert verify_password("s3cret", "scrypt$16384$8") is False

    # Non-hex salt.
    assert verify_password("s3cret", "scrypt$" + n + "$" + r + "$" + p + "$notahex$" + hash_hex) is False

    # Non-hex hash.
    assert verify_password("s3cret", "scrypt$" + n + "$" + r + "$" + p + "$" + salt_hex + "$notahex") is False

    # Non-int params.
    assert verify_password("s3cret", "scrypt$notanint$" + r + "$" + p + "$" + salt_hex + "$" + hash_hex) is False

    # Valid roundtrip still works.
    assert verify_password("s3cret", valid) is True
