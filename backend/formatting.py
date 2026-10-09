"""
Output formatting shared by preprocess, the service layer and the CLI.

  json_safe(value)   plain-Python, JSON-serialisable copy of nested data
"""
import math
from datetime import date, datetime

import numpy as np
import pandas as pd


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
