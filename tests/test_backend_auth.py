import time

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import backend.auth.tokens as tokens
from backend.main import app

client = TestClient(app)

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


def _install_fake_jwks(monkeypatch):
    monkeypatch.setattr(tokens, "_jwk_client", _FakeJWKClient(_PUBLIC_PEM))


def _make_token(sub="user-123", email="fin@example.com", expires_in=3600):
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return pyjwt.encode(claims, _PRIVATE_PEM, algorithm="RS256", headers={"kid": "test-kid"})


def test_me_happy_path(monkeypatch):
    _install_fake_jwks(monkeypatch)
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {_make_token()}"}
    )
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123", "email": "fin@example.com"}


def test_me_requires_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"] == "Authentication required"


def test_me_rejects_expired_token(monkeypatch):
    _install_fake_jwks(monkeypatch)
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {_make_token(expires_in=-10)}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired token"


def test_me_rejects_garbage_token(monkeypatch):
    _install_fake_jwks(monkeypatch)
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired token"


def test_me_rejects_token_signed_by_foreign_key(monkeypatch):
    _install_fake_jwks(monkeypatch)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "attacker", "exp": now + 600},
        other_pem,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired token"


def test_me_accepts_es256_token(monkeypatch):
    """Verify the backend accepts ES256 tokens (the algorithm Supabase actually uses)."""
    # Install the RSA-based fake JWKS (as the test does) — but verify the verify_access_token
    # function can still validate an ES256 token by fetching the correct key from the JWKS.
    # Since our fake JWKS only has RSA keys, an ES256 token should fail verification
    # because the key won't match — but we want to ensure the code path attempts ES256.
    # Instead, let's test that when we *do* have a matching ES256 key in the JWKS, it works.
    from cryptography.hazmat.primitives.asymmetric import ec

    # Generate an EC key pair
    ec_private_key = ec.generate_private_key(ec.SECP256R1())
    ec_private_pem = ec_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ec_public_pem = ec_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Override the fake JWKS to return our EC public key
    monkeypatch.setattr(tokens, "_jwk_client", _FakeJWKClient(ec_public_pem))

    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "user-123", "email": "fin@example.com", "exp": now + 3600},
        ec_private_pem,
        algorithm="ES256",
        headers={"kid": "test-kid", "alg": "ES256"},
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123", "email": "fin@example.com"}
