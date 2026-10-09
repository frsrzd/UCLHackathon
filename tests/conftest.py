"""
Shared hand-built test data. Unit tests use these small made-up frames, never the
real dataset (only tests/test_integration.py and the viewer's build_source test
touch the committed data files).
"""
import numpy as np
import pandas as pd
import pytest

from backend import features
from backend.tactics import TACTICS, TARGET, enabled_tactics


def make_stats(n=6, seed=0):
    """A small frame shaped like data/processed/centers_stats.csv for n made-up
    centers, with numpy dtypes and a blank age, as the real file has."""
    rng = np.random.default_rng(seed)
    stats = pd.DataFrame({
        "nflId": np.arange(1001, 1001 + n, dtype=np.int64),
        "name": [f"Center {i}" for i in range(n)],
        "team": [f"T{i:02d}" for i in range(n)],
        "age": pd.array([25, None] + [30] * (n - 2), dtype="Int64"),
        "height_in": pd.array([75] * n, dtype="Int64"),
        "weight_lb": pd.array(rng.integers(290, 331, n), dtype="Int64"),
        "base_snaps": rng.integers(150, 340, n),
    })
    for tactic in TACTICS.values():
        stats[f"{tactic['prefix']}_snaps"] = rng.integers(0, 120, n)
        for attr in tactic["attributes"]:
            if attr.better != TARGET and attr.key not in stats:
                low, high = (0.0, 0.2) if attr.format == "pct" else (1.0, 4.0)
                stats[attr.key] = rng.uniform(low, high, n)
    return stats


def make_processed(tracking_used=True, n=6):
    """(stats, benchmarks, meta) as service.load_processed() returns them."""
    stats = make_stats(n)
    tactics = enabled_tactics(tracking_used)
    benchmarks = features.benchmarks(stats, tactics, tracking_used)
    meta = {"trackingUsed": tracking_used, "enabledTactics": list(tactics),
            "generatedAt": "2026-01-01T00:00:00+00:00",
            "rowCounts": {"qualifyingCenters": n}}
    return stats, benchmarks, meta


@pytest.fixture
def processed():
    return make_processed(tracking_used=True)


@pytest.fixture
def processed_no_tracking():
    return make_processed(tracking_used=False)
