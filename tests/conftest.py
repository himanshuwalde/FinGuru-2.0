"""Shared fixtures: a fake Supabase JWKS so tests can mint valid-looking RS256 tokens."""
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import backend.auth.tokens as tokens

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_PUBLIC_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Stands in for the Supabase JWKS: advertises the test public key."""

    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._key)


@pytest.fixture
def fake_jwks(monkeypatch):
    monkeypatch.setattr(tokens, "_jwk_client", _FakeJWKClient(_PUBLIC_PEM))


def make_token(sub="user-123", email="fin@example.com", expires_in=3600) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return pyjwt.encode(claims, _PRIVATE_PEM, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def auth_headers(fake_jwks) -> dict:
    return {"Authorization": f"Bearer {make_token()}"}
