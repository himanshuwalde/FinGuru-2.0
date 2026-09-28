"""Shared fixtures: a fake Supabase JWKS so tests can mint valid-looking RS256 and ES256 tokens."""
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

import backend.auth.tokens as tokens

# --- RSA key pair (RS256) ---
_RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_PRIVATE_PEM = _RSA_PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_RSA_PUBLIC_PEM = _RSA_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

# --- EC key pair (ES256) — mimics Supabase's actual key type ---
_EC_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_EC_PRIVATE_PEM = _EC_PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_EC_PUBLIC_PEM = _EC_PRIVATE_KEY.public_key().public_bytes(
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
    monkeypatch.setattr(tokens, "_jwk_client", _FakeJWKClient(_RSA_PUBLIC_PEM))


def make_token(sub="user-123", email="fin@example.com", expires_in=3600) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return pyjwt.encode(claims, _RSA_PRIVATE_PEM, algorithm="RS256", headers={"kid": "test-kid"})


def make_es256_token(sub="user-123", email="fin@example.com", expires_in=3600) -> str:
    """Generate an ES256 token — the algorithm Supabase actually uses."""
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return pyjwt.encode(claims, _EC_PRIVATE_PEM, algorithm="ES256", headers={"kid": "test-kid", "alg": "ES256", "typ": "JWT"})


@pytest.fixture
def auth_headers(fake_jwks) -> dict:
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def es256_auth_headers(fake_jwks) -> dict:
    """Auth headers using an ES256 token (mimics Supabase JWTs)."""
    return {"Authorization": f"Bearer {make_es256_token()}"}


@pytest.fixture
def es256_fake_jwks(monkeypatch):
    """A fake JWKS that advertises the ES256 test key — mimics Supabase's actual key type."""
    monkeypatch.setattr(tokens, "_jwk_client", _FakeJWKClient(_EC_PUBLIC_PEM))
