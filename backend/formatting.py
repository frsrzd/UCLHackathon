"""
Output formatting shared by preprocess, the service layer and the CLI.

  display(value, fmt)  text shown for a value: pct "3.1%", lb "306 lb",
                       speed "3.2 yd/s", yd "1.4 yd"; a blank value shows as "—"
  json_safe(value)     plain-Python, JSON-serialisable copy of nested data
"""
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

MISSING = "—"

DISPLAY = {
    "pct": lambda v: f"{v * 100:.1f}%",     # rates are stored as fractions: 0.0312 -> "3.1%"
    "lb": lambda v: f"{v:.0f} lb",
    "speed": lambda v: f"{v:.1f} yd/s",
    "yd": lambda v: f"{v:.1f} yd",
}


def display(value, fmt):
    """Display text for `value` in format `fmt` (a key of DISPLAY)."""
    if value is None or pd.isna(value):
        return MISSING
    return DISPLAY[fmt](float(value))


def json_safe(value):
    """Recursively convert numpy/pandas scalars to int/float/bool/str, and NaN, NA
    or NaT to None, so json.dumps never sees a numpy type or a NaN."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
