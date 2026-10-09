import json

import pytest

from backend import service
from backend.tactics import TACTICS

PLAIN_TYPES = (str, int, float, bool, type(None))


def assert_plain(value):
    """Only dict / list / str / int / float / bool / None anywhere: no numpy types."""
    if isinstance(value, dict):
        for v in value.values():
            assert_plain(v)
    elif isinstance(value, list):
        for v in value:
            assert_plain(v)
    else:
        assert type(value) in PLAIN_TYPES, f"{value!r} is a {type(value)}"


@pytest.mark.parametrize("tactic_key", list(TACTICS))
def test_rankings_are_json_serialisable_without_numpy_or_nan(processed, tactic_key):
    result = service.build_rankings(*processed, tactic_key, limit=50)

    json.dumps(result, allow_nan=False)            # raises on NaN or numpy types
    assert_plain(result)
    assert list(result) == ["tactic", "tacticName", "trackingUsed", "columns", "players"]
    player = result["players"][0]
    assert all(isinstance(a["score"], int) and 0 <= a["score"] <= 100
               for a in player["attributes"].values())


def test_blank_age_becomes_null(processed):
    players = service.build_rankings(*processed, "dropback", limit=50)["players"]
    assert None in [p["age"] for p in players]


def test_limit_and_contract_fields(processed):
    result = service.build_rankings(*processed, "stunt_twist", limit=3)

    assert len(result["players"]) == 3
    assert [p["rank"] for p in result["players"]] == [1, 2, 3]
    assert [c["key"] for c in result["columns"]] == [
        "sw_loss_rate", "sw_pressure_rate", "loss_rate", "penalty_rate", "weight_lb"]
    assert result["columns"][-1]["target"] == 305
    assert result["trackingUsed"] is False         # this tactic uses no tracking attribute


@pytest.mark.parametrize("limit", [0, 51, -1, 2.5, "10", True])
def test_bad_limits_are_rejected(processed, limit):
    with pytest.raises(service.InvalidLimit):
        service.build_rankings(*processed, "dropback", limit=limit)


def test_unknown_tactic_is_rejected(processed):
    with pytest.raises(service.UnknownTactic, match="Valid tactics"):
        service.build_rankings(*processed, "nope")


def test_tracking_tactic_is_unavailable_without_tracking(processed_no_tracking):
    keys = [t["key"] for t in service.list_tactics(processed_no_tracking[2])]

    assert "long_dev" not in keys
    with pytest.raises(service.UnknownTactic, match="needs tracking"):
        service.build_rankings(*processed_no_tracking, "long_dev")
    rollout = service.build_rankings(*processed_no_tracking, "rollout")
    assert "lateral_speed" not in [c["key"] for c in rollout["columns"]]
    assert sum(c["weight"] for c in rollout["columns"]) == pytest.approx(1.0)
