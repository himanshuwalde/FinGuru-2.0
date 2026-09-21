from fastapi import APIRouter

from backend.schemas.common import PillarStatus

router = APIRouter(prefix="/ai-cfo", tags=["ai-cfo"])

_MODULES = [
    "grounded_chat",
    "affordability_queries",
    "portfolio_scorecard",
    "stock_lookup",
    "general_knowledge",
    "explain_score_panel",
    "chat_sessions",
]


@router.get("/status", response_model=PillarStatus)
def ai_cfo_status() -> PillarStatus:
    return PillarStatus(pillar="ai-cfo", modules=_MODULES)
