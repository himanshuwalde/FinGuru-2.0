"""FastAPI dependency that derives the acting user from the verified JWT."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.tokens import AuthUser, TokenVerificationError, verify_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return verify_access_token(credentials.credentials)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


class AuthContext:
    """The verified user plus the raw access token (needed to build a
    user-scoped Supabase client)."""

    __slots__ = ("user", "access_token")

    def __init__(self, user: AuthUser, access_token: str):
        self.user = user
        self.access_token = access_token


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        user = verify_access_token(credentials.credentials)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return AuthContext(user=user, access_token=credentials.credentials)
