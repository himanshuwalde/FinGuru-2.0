"""User-scoped Supabase clients for the API layer.

Every request builds a client whose PostgREST calls carry the user's verified
JWT as the Authorization header, so Row-Level Security applies exactly as it
does in the Streamlit app — while every query still filters by user_id
explicitly (defense in depth).
"""
from supabase import Client, create_client

from backend.config import get_settings


class SupabaseNotConfigured(RuntimeError):
    pass


def user_client(access_token: str) -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_KEY are not configured on the backend"
        )
    client = create_client(settings.supabase_url, settings.supabase_key)
    # Scope every PostgREST call to the authenticated user (RLS enforced
    # server-side against this token).
    client.postgrest.auth(access_token)
    return client
