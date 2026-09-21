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
