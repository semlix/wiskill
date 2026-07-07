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
