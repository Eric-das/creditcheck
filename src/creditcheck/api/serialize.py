"""JSON-safe conversion for engine results.

The engines return rich Python types the standard JSON encoder cannot handle:
  * Decimal  - every money value (2-dp, exact) -> float for the wire
  * date/datetime - transaction & due dates    -> ISO 'YYYY-MM-DD' string
Everything else passes through untouched.
"""
from __future__ import annotations

import datetime
from decimal import Decimal


def to_jsonable(obj):
    """Recursively convert Decimal/date to JSON-serialisable primitives."""
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj
