from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth import AuthUser, get_current_user
from backend.schemas.common import PillarStatus

router = APIRouter(prefix="/auth", tags=["auth"])

_MODULES = ["login", "signup", "password_reset", "jwt_verification"]


class AuthMeResponse(BaseModel):
    user_id: str
    email: str | None


@router.get("/status", response_model=PillarStatus)
def auth_status() -> PillarStatus:
    return PillarStatus(pillar="auth", modules=_MODULES)


@router.get("/me", response_model=AuthMeResponse)
def me(user: AuthUser = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse(user_id=user.id, email=user.email)
