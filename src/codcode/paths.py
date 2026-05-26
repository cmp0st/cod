"""XDG-style directory constants for cod."""

from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "cod"
DATA_DIR = Path.home() / ".local" / "share" / "cod"
STATE_DIR = Path.home() / ".local" / "state" / "cod"

MODELS_DIR = DATA_DIR / "models"
LOG_DIR = STATE_DIR
CACHE_DIR = STATE_DIR / "cache"


def ensure_dirs() -> None:
    """Create all required application directories if they don't exist."""
    for d in (CONFIG_DIR, DATA_DIR, STATE_DIR, MODELS_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
