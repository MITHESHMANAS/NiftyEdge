"""
src/etl/config.py

Loads configuration from `.env` (falling back to sensible defaults so the
pipeline still runs out-of-the-box without one). All hardcoded paths that
previously lived in loader.py now come from here.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env from the project root if present. Does not override variables
# already set in the real environment (e.g. by CI).
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(key: str, default: str) -> Path:
    val = os.getenv(key, default)
    p = Path(val)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


DB_PATH: Path = _env_path("DB_PATH", "data/nifty100.db")
RAW_DATA_PATH: Path = _env_path("RAW_DATA_PATH", "data/raw")
SUPPLEMENTARY_DATA_PATH: Path = _env_path("SUPPLEMENTARY_DATA_PATH", "data/raw/supporting_datasets")
OUTPUT_PATH: Path = _env_path("OUTPUT_PATH", "output")
LOG_PATH: Path = _env_path("LOG_PATH", "logs")
SCHEMA_PATH: Path = _env_path("SCHEMA_PATH", "db/schema.sql")

# Shorter aliases used throughout loader.py
RAW_DIR = RAW_DATA_PATH
SUPP_DIR = SUPPLEMENTARY_DATA_PATH
OUTPUT_DIR = OUTPUT_PATH

PORT: int = int(os.getenv("PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
VALIDATE_URLS: bool = _env_bool("VALIDATE_URLS", False)
