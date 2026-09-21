"""FinGuru FastAPI backend package."""
import sys
from pathlib import Path

# engines/, services/, ai/ and utils/ stay at the repo root while the legacy
# Streamlit app is still live (they move under backend/ in the final cleanup
# phase). Inserting the repo root on sys.path lets the API layer import them
# unchanged regardless of the directory uvicorn or pytest is launched from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
