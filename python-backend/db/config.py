"""Database configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip().strip('"').strip("'") if value else default


DATABASE_URL = _env(
    "DATABASE_URL",
    "postgresql://airline:airline@localhost:5432/airline",
)
