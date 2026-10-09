import numpy as np
import pandas as pd
import pytest

from backend.tactics import TACTICS, TRACKING_ATTRIBUTES, active_attributes, enabled_tactics, tactic_mask


@pytest.mark.parametrize("tracking_used", [True, False])
def test_weights_sum_to_one_per_tactic(tracking_used):
    for tactic in enabled_tactics(tracking_used).values():
        weights = [a.weight for a in active_attributes(tactic, tracking_used)]
        assert sum(weights) == pytest.approx(1.0)


def test_without_tracking_tracking_attributes_are_dropped_and_weights_rescaled():
    attrs = active_attributes(TACTICS["rollout"], tracking_used=False)

    assert not {a.key for a in attrs} & TRACKING_ATTRIBUTES
    # 35, 20, 10, 10, 5 out of the 80 left once lateral_speed (20) is dropped
    assert [a.weight for a in attrs] == pytest.approx([0.4375, 0.25, 0.125, 0.125, 0.0625])
    assert [a.key for a in attrs] == ["rollout_loss_rate", "rollout_pressure_rate",
                                      "loss_rate", "weight_lb", "penalty_rate"]


def test_tracking_only_tactic_is_disabled_without_tracking():
    assert "long_dev" in enabled_tactics(tracking_used=True)
    assert "long_dev" not in enabled_tactics(tracking_used=False)


def test_tactic_filters_keep_only_the_intended_snaps():
    rows = [  # blockType, playAction, dropBackType,         rushers, time_to_event
        ("PP", 0, "TRADITIONAL", 4, 2.0),              # 0 dropback
        ("PP", 1, "TRADITIONAL", 4, 2.0),              # 1 play_action (not dropback)
        ("PP", 0, "SCRAMBLE", 4, 2.0),                 # 2 nothing
        ("PR", 0, "TRADITIONAL", 4, 2.0),              # 3 rollout via pocket-roll block
        ("PP", 0, "DESIGNED_ROLLOUT_LEFT", 4, 2.0),    # 4 rollout via designed rollout
        ("PP", 0, "SCRAMBLE_ROLLOUT_RIGHT", 4, 2.0),   # 5 nothing: scrambles excluded
        ("SW", 0, "TRADITIONAL", 4, 2.0),              # 6 stunt_twist
        ("PP", 0, "TRADITIONAL", 5, 2.0),              # 7 dropback + blitz
        (None, 0, None, 4, np.nan),                    # 8 blanks never match
        ("PP", 0, "TRADITIONAL", 4, 3.0),              # 9 dropback + long_dev (>= 3.0 s)
        ("PP", 0, "TRADITIONAL", 4, 2.9),              # 10 dropback only
    ]
    snaps = pd.DataFrame(rows, columns=["pff_blockType", "pff_playAction", "dropBackType",
                                        "n_rushers", "time_to_event"])
    snaps["pff_playAction"] = snaps["pff_playAction"].astype("Int64")

    def kept(key):
        return list(snaps.index[tactic_mask(TACTICS[key], snaps)])

    assert kept("dropback") == [0, 7, 9, 10]
    assert kept("play_action") == [1]
    assert kept("rollout") == [3, 4]
    assert kept("stunt_twist") == [6]
    assert kept("blitz") == [7]
    assert kept("long_dev") == [9]
