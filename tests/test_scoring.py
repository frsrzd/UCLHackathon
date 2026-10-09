import numpy as np
import pandas as pd
import pytest

from backend import scoring
from backend.tactics import TACTICS, Attribute, active_attributes

LOWER = Attribute("loss_rate", "Loss rate", 1.0, "lower", "pct")
HIGHER = Attribute("lateral_speed", "Lateral speed", 1.0, "higher", "speed")
TARGET = Attribute("weight_lb", "Weight", 1.0, "target", "lb", target=305)


def scores(attr, values, bench=None):
    return list(scoring.attribute_scores(pd.Series(values, dtype=float), attr, bench))


def test_lower_is_better():
    bench = {"ideal": 0.02, "floor": 0.10}
    assert scores(LOWER, [0.02, 0.10, 0.06, 0.01, 0.20], bench) == pytest.approx(
        [1.0, 0.0, 0.5, 1.0, 0.0])                # clipped to 0..1 beyond ideal/floor


def test_higher_is_better():
    bench = {"ideal": 3.0, "floor": 1.0}
    assert scores(HIGHER, [3.0, 1.0, 2.0, 4.0, 0.5], bench) == pytest.approx(
        [1.0, 0.0, 0.5, 1.0, 0.0])


def test_target_full_within_5_and_zero_from_25():
    # 1 within +-5 lb of 305, then (25 - distance) / 20 down to 0 at +-25 lb
    assert scores(TARGET, [305, 310, 300, 315, 320, 290, 330, 280, 340]) == pytest.approx(
        [1.0, 1.0, 1.0, 0.75, 0.5, 0.5, 0.0, 0.0, 0.0])


def test_ideal_equal_to_floor_and_missing_values_are_neutral():
    assert scores(LOWER, [0.01, 0.5], {"ideal": 0.05, "floor": 0.05}) == [0.5, 0.5]
    assert scores(LOWER, [np.nan], {"ideal": 0.02, "floor": 0.10}) == [0.5]
    assert scores(TARGET, [np.nan]) == [0.5]


def test_round_half_up():
    assert scoring.round_half_up(2.25, 1) == 2.3
    assert scoring.round_half_up(84.25, 1) == 84.3
    assert scoring.round_half_up(0.5) == 1.0


def test_confidence_bands():
    assert [scoring.confidence(n) for n in [0, 24, 25, 59, 60, 200]] == [
        "Low", "Low", "Medium", "Medium", "High", "High"]


@pytest.mark.parametrize("tactic_key", list(TACTICS))
def test_suitability_in_range_and_ranks_without_gaps(processed, tactic_key):
    stats, benchmarks, _ = processed
    tactic = TACTICS[tactic_key]
    ranked = scoring.score_tactic(stats, tactic, active_attributes(tactic, True), benchmarks)

    assert ranked["suitability"].between(0, 100).all()
    assert list(ranked["rank"]) == list(range(1, len(stats) + 1))
    assert ranked["suitability"].is_monotonic_decreasing


def test_ties_break_on_tactic_snaps_then_base_snaps():
    tactic = TACTICS["stunt_twist"]
    attrs = active_attributes(tactic, True)
    same = {"sw_loss_rate": 0.05, "sw_pressure_rate": 0.03, "loss_rate": 0.06,
            "penalty_rate": 0.002, "weight_lb": 305}
    stats = pd.DataFrame([
        {"nflId": 1, "sw_snaps": 10, "base_snaps": 300, **same},
        {"nflId": 2, "sw_snaps": 30, "base_snaps": 200, **same},   # most tactic snaps
        {"nflId": 3, "sw_snaps": 10, "base_snaps": 320, **same},   # beats 1 on base snaps
    ])
    bench = {k: {"ideal": 0.0, "floor": 0.1} for k in same if k != "weight_lb"}
    ranked = scoring.score_tactic(stats, tactic, attrs, bench)

    assert ranked["suitability"].nunique() == 1
    assert list(ranked["nflId"]) == [2, 3, 1]


def test_strength_and_concern_use_weight_times_score():
    tactic = TACTICS["stunt_twist"]
    attrs = active_attributes(tactic, True)
    stats = pd.DataFrame([{"nflId": 1, "sw_snaps": 10, "base_snaps": 200,
                           "sw_loss_rate": 0.0,      # best possible, weight 0.40
                           "sw_pressure_rate": 0.1,  # worst possible, weight 0.25
                           "loss_rate": 0.05, "penalty_rate": 0.05, "weight_lb": 305}])
    bench = {k: {"ideal": 0.0, "floor": 0.1}
             for k in ["sw_loss_rate", "sw_pressure_rate", "loss_rate", "penalty_rate"]}
    row = scoring.score_tactic(stats, tactic, attrs, bench).iloc[0]

    assert row["top_strength"] == "sw_loss_rate"         # 0.40 x 1.0
    assert row["biggest_concern"] == "sw_pressure_rate"  # 0.25 x (1 - 0)
    # 100 x (0.40x1 + 0.25x0 + 0.15x0.5 + 0.10x0.5 + 0.10x1) = 62.5
    assert row["suitability"] == 62.5
