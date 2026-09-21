from fastapi import APIRouter

from backend.schemas.common import PillarStatus

router = APIRouter(prefix="/protect", tags=["protect"])

_MODULES = [
    "insurance_advisor",
    "financial_guardrail",
    "family_legacy",
    "web3_vault",
]


@router.get("/status", response_model=PillarStatus)
def protect_status() -> PillarStatus:
    return PillarStatus(pillar="protect", modules=_MODULES)
