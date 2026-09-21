from fastapi import APIRouter

from backend.schemas.common import PillarStatus

router = APIRouter(prefix="/learn", tags=["learn"])

_MODULES = [
    "money_school_lessons",
    "contextual_glossary",
    "quizzes",
    "gamification",
    "leaderboard",
    "weekly_challenges",
]


@router.get("/status", response_model=PillarStatus)
def learn_status() -> PillarStatus:
    return PillarStatus(pillar="learn", modules=_MODULES)
