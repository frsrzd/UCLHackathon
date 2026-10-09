import numpy as np
import pandas as pd
import pytest

from backend import config, features
from backend.tactics import TACTICS


def test_shrinkage_formula_known_answer():
    # (events + k * prior) / (snaps + k) = (10 + 50 * 0.05) / (100 + 50)
    assert features.shrink(10, 100, 0.05, 50) == pytest.approx(12.5 / 150)
    # no snaps at all gives exactly the prior
    assert features.shrink(0, 0, 0.07, 20) == pytest.approx(0.07)


def test_flags_treat_blanks_as_zero_and_match_fouls_safely():
    snaps = pd.DataFrame({
        "nflId": [1, 1, 1, 2],
        "pff_beatenByDefender": [1.0, 0.0, np.nan, 0.0],
        "pff_hitAllowed": [0.0, 0.0, np.nan, 0.0],
        "pff_hurryAllowed": [0.0, 1.0, np.nan, 0.0],
        "pff_sackAllowed": [0.0, 0.0, np.nan, 1.0],
        "foulNFLId1": pd.array([None, 1, None, 9], dtype="Int64"),
        "foulNFLId2": pd.array([None, None, None, 2], dtype="Int64"),
        "foulNFLId3": pd.array([None, None, None, None], dtype="Int64"),
    })
    out = features.add_flags(snaps)

    assert list(out["loss"]) == [1, 1, 0, 1]       # beaten counts as a loss only
    assert list(out["pressure"]) == [0, 1, 0, 1]   # hit, hurry or sack
    assert list(out["sack"]) == [0, 0, 0, 1]
    assert list(out["penalty"]) == [0, 1, 0, 1]    # his id in any foul column


def hand_built_snaps():
    """Center 1: 4 snaps, 1 loss and 1 penalty, 2 of them switch blocks (1 lost).
    Center 2: 4 clean snaps, none of them switch blocks."""
    return pd.DataFrame({
        "gameId": 1, "playId": range(8),
        "nflId": [1, 1, 1, 1, 2, 2, 2, 2],
        "possessionTeam": ["KC", "KC", "KC", "LV", "LV", "LV", "LV", "LV"],
        "pff_blockType": ["SW", "SW", "PP", "PP", "PP", "PP", "PP", "PP"],
        "loss": [1, 0, 0, 0, 0, 0, 0, 0],
        "pressure": [1, 0, 0, 0, 0, 0, 0, 0],
        "sack": [0] * 8,
        "penalty": [0, 0, 0, 1, 0, 0, 0, 0],
    })


def hand_built_players():
    return pd.DataFrame({
        "nflId": [1, 2], "displayName": ["A", "B"],
        "birthDate": pd.to_datetime(["1995-09-02", None]),
        "height_in": pd.array([75, 76], dtype="Int64"),
        "weight": pd.array([300, 310], dtype="Int64"),
    })


def test_overall_and_tactic_rates_match_hand_calculation():
    stats = features.center_stats(hand_built_snaps(), hand_built_players(),
                                  {"stunt_twist": TACTICS["stunt_twist"]})
    k_all, k_tac = config.K_OVERALL, config.K_TACTIC
    league_loss = 1 / 8                               # pooled over both centers' 8 snaps

    a_loss = (1 + k_all * league_loss) / (4 + k_all)
    b_loss = (0 + k_all * league_loss) / (4 + k_all)
    assert stats.loc[1, "loss_rate"] == pytest.approx(a_loss)
    assert stats.loc[2, "loss_rate"] == pytest.approx(b_loss)
    # tactic rate shrinks toward his own overall rate...
    assert stats.loc[1, "sw_snaps"] == 2
    assert stats.loc[1, "sw_loss_rate"] == pytest.approx((1 + k_tac * a_loss) / (2 + k_tac))
    # ...so with 0 tactic snaps it equals that overall rate
    assert stats.loc[2, "sw_snaps"] == 0
    assert stats.loc[2, "sw_loss_rate"] == pytest.approx(b_loss)
    # penalty rate is overall only
    assert stats.loc[1, "penalty_rate"] == pytest.approx((1 + k_all * 1 / 8) / (4 + k_all))


def test_profile_team_age_and_counts():
    stats = features.center_stats(hand_built_snaps(), hand_built_players(),
                                  {"stunt_twist": TACTICS["stunt_twist"]})

    assert stats.loc[1, "team"] == "KC"               # 3 of his 4 snaps
    assert stats.loc[1, "base_snaps"] == 4 and stats.loc[1, "losses"] == 1
    assert stats.loc[1, "age"] == 25                  # turns 26 a day after AGE_AS_OF
    assert pd.isna(stats.loc[2, "age"])               # blank birth date
    assert stats.loc[2, "weight_lb"] == 310


def test_age_counts_whole_years_on_the_reference_date():
    born = pd.Series(pd.to_datetime(["2000-09-01", "2000-09-02", None]))
    ages = features.age_on(born, "2021-09-01")

    assert ages[0] == 21                    # birthday on the reference date counts
    assert ages[1] == 20                    # birthday the day after does not
    assert pd.isna(ages[2])


def test_benchmarks_use_10th_and_90th_percentiles():
    stats = pd.DataFrame({"loss_rate": np.linspace(0.0, 0.10, 11),
                          "lateral_speed": np.linspace(1.0, 3.0, 11)})
    # a cut-down rollout tactic holding one lower- and one higher-is-better attribute
    rollout = {"rollout": {**TACTICS["rollout"], "attributes": [
        a for a in TACTICS["rollout"]["attributes"] if a.key in ("loss_rate", "lateral_speed")]}}
    bench = features.benchmarks(stats, rollout, tracking_used=True)

    assert bench["loss_rate"]["ideal"] == pytest.approx(0.01)      # lower: ideal = p10
    assert bench["loss_rate"]["floor"] == pytest.approx(0.09)      # floor = p90
    assert bench["lateral_speed"]["ideal"] == pytest.approx(2.8)   # higher: ideal = p90
    assert bench["lateral_speed"]["floor"] == pytest.approx(1.2)   # floor = p10
