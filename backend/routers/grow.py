from fastapi import APIRouter

from backend.schemas.common import PillarStatus

router = APIRouter(prefix="/grow", tags=["grow"])

_MODULES = [
    "portfolio_tracker",
    "concentration_benchmark_score",
    "holdings_news_feed",
    "fire_planner",
    "financial_twin",
    "income_stop_runway",
    "tax_planner",
    "trust_engine",
    "calculators_hub",
    "card_rewards_optimizer",
    "mutual_fund_explorer",
    "fd_discovery",
    "basket_explorer",
]


@router.get("/status", response_model=PillarStatus)
def grow_status() -> PillarStatus:
    return PillarStatus(pillar="grow", modules=_MODULES)
