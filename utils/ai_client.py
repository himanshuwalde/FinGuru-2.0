"""
Centralized AI Client for Google Gemini API interactions.
Provides model selection, configuration, and error handling in one place.
Works in both Streamlit app context and standalone scripts (like alert_engine.py).
"""
import os
import functools
import logging
from typing import Optional, List

import google.generativeai as genai

# Configure logging for standalone scripts
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import streamlit, but make it optional
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    st = None


def _get_api_key() -> str:
    """Get API key from environment (standalone) or Streamlit secrets (app)."""
    # First try environment variable (works in both contexts)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return api_key

    # Fallback to Streamlit secrets if available
    if HAS_STREAMLIT and hasattr(st, 'secrets'):
        api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
        if api_key:
            return api_key

    raise ValueError("GEMINI_API_KEY not found in environment variables or Streamlit secrets")


# Cache the Gemini client configuration
if HAS_STREAMLIT:
    @st.cache_resource
    def get_gemini_client():
        """Initialize and return configured Gemini client."""
        api_key = _get_api_key()
        genai.configure(api_key=api_key)
        return genai
else:
    # Use functools.lru_cache for standalone scripts
    @functools.lru_cache(maxsize=1)
    def get_gemini_client():
        """Initialize and return configured Gemini client."""
        api_key = _get_api_key()
        genai.configure(api_key=api_key)
        return genai


def _warn(message: str):
    """Log warning in both Streamlit and standalone contexts."""
    if HAS_STREAMLIT and st:
        st.warning(message)
    else:
        logger.warning(message)


if HAS_STREAMLIT:
    @st.cache_data(ttl=3600)  # Cache model list for 1 hour
    def get_available_models(_genai_client) -> List[str]:
        """Fetch all models that support generateContent."""
        try:
            models = _genai_client.list_models()
            return [m.name.replace('models/', '') for m in models if 'generateContent' in m.supported_generation_methods]
        except Exception as e:
            _warn(f"Could not fetch models: {e}")
            return []
else:
    @functools.lru_cache(maxsize=1)
    def get_available_models(_genai_client) -> List[str]:
        """Fetch all models that support generateContent."""
        try:
            models = _genai_client.list_models()
            return [m.name.replace('models/', '') for m in models if 'generateContent' in m.supported_generation_methods]
        except Exception as e:
            _warn(f"Could not fetch models: {e}")
            return []


def get_best_model(_genai_client, prefer_flash: bool = True) -> str:
    """
    Select the best available model based on preferences.

    Args:
        _genai_client: The configured genai client
        prefer_flash: If True, prefers 'flash' models for speed/cost

    Returns:
        Model name string
    """
    valid_models = get_available_models(_genai_client)

    if not valid_models:
        return "gemini-1.5-flash"  # Safe default

    if prefer_flash:
        # Try to find a flash model
        flash_models = [m for m in valid_models if 'flash' in m.lower()]
        if flash_models:
            # Prefer 1.5-flash or 2.0-flash
            for pref in ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-2.5-flash']:
                if pref in flash_models:
                    return pref
            return flash_models[0]

    # Fallback: prefer pro models, then first available
    pro_models = [m for m in valid_models if 'pro' in m.lower()]
    if pro_models:
        return pro_models[0]

    return valid_models[0]


def get_generative_model(_genai_client, model_name: Optional[str] = None, prefer_flash: bool = True):
    """
    Get a configured GenerativeModel instance.

    Args:
        _genai_client: The configured genai client
        model_name: Specific model to use (overrides auto-selection)
        prefer_flash: If True and no model_name given, prefers flash models

    Returns:
        Configured GenerativeModel instance
    """
    if model_name is None:
        model_name = get_best_model(_genai_client, prefer_flash)
    return _genai_client.GenerativeModel(model_name)


def generate_content_safe(model, prompt: str, max_retries: int = 2) -> Optional[str]:
    """
    Generate content with retry logic and error handling.

    Returns the generated text, or None on failure. Failures are written to the
    app/console logs only — never shown as a red Streamlit error banner —
    because callers fall back to a deterministic answer and surface a friendly
    note instead (a quota-exceeded or offline Gemini call shouldn't alarm the
    user).

    Args:
        model: GenerativeModel instance
        prompt: The prompt to send
        max_retries: Number of retry attempts

    Returns:
        Generated text or None if failed
    """
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt)
            if response.text:
                return response.text
            elif attempt < max_retries:
                continue
        except Exception as e:
            if attempt == max_retries:
                # Log for debugging, but never surface a red error banner in
                # the UI — the caller falls back to a deterministic answer.
                logger.error("AI generation failed after %d attempts: %s",
                             max_retries + 1, e)
                return None
    return None