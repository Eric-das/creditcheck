"""Load runtime configuration (Sage DSN, credentials) from config.json.

config.json is git-ignored: it holds credentials and must never be committed.
Start from config.example.json.
"""

from __future__ import annotations

import json
from pathlib import Path

# Repo root = two levels up from src/creditcheck/config.py
_DEFAULT = Path(__file__).resolve().parents[2] / "config.json"


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else _DEFAULT
    if not p.exists():
        raise FileNotFoundError(
            f"Config not found at {p}. "
            "Copy config.example.json to config.json and fill it in."
        )
    return json.loads(p.read_text(encoding="utf-8"))
