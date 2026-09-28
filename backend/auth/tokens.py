"""Verify Supabase access tokens (RS256 or ES256) against the project's JWKS."""
import jwt
from jwt import PyJWKClient

from backend.config import get_settings


class TokenVerificationError(Exception):
    """Raised when a bearer token fails verification."""


class AuthUser:
    __slots__ = ("id", "email")

    def __init__(self, id: str, email: str | None):
        self.id = id
        self.email = email


_jwk_client: PyJWKClient | None = None


def get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        url = get_settings().supabase_url
        if not url:
            raise TokenVerificationError("SUPABASE_URL is not configured")
        _jwk_client = PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True)
    return _jwk_client


def verify_access_token(token: str) -> AuthUser:
    try:
        client = get_jwk_client()
        signing_key = client.get_signing_key_from_jwt(token)
        # Supabase projects may use RS256 or ES256 depending on the project config.
        # Allow both — the JWKS key type determines which algorithm is used.
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            options={"verify_aud": False},
        )
    except TokenVerificationError:
        raise
    except Exception as exc:
        raise TokenVerificationError("Invalid or expired token") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise TokenVerificationError("Token missing subject claim")
    email = claims.get("email")
    return AuthUser(id=sub, email=email if isinstance(email, str) else None)
