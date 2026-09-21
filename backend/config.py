"""Backend configuration, sourced from the repo-root .env (gitignored)."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

_REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(_REPO_ROOT / ".env")

_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class Settings(BaseModel):
    api_prefix: str = "/api"
    cors_origins: tuple[str, ...] = _DEFAULT_CORS_ORIGINS
    supabase_url: str = ""
    supabase_key: str = ""


@lru_cache
def get_settings() -> Settings:
    raw_origins = os.environ.get("CORS_ORIGINS", "")
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())
    return Settings(
        cors_origins=origins or _DEFAULT_CORS_ORIGINS,
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
    )
