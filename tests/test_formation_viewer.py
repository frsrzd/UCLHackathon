from pathlib import Path

import pandas as pd

from backend.formation_viewer import (
    TACTIC_ATTRIBUTES,
    DemoSource,
    RealSource,
    build_source,
    frame_status,
    format_tactic_metrics,
    player_options,
    tactic_metric_values,
)


def test_all_attribute_orders_match_user_priorities():
    expected = {
        "Traditional dropback": (
            "Loss rate", "Pressure rate", "Sack rate", "Weight", "Penalty rate",
        ),
        "Play-action": (
            "PA loss rate", "PA pressure rate", "Overall loss rate",
            "PA sack rate", "Weight", "Penalty rate",
        ),
        "Rollouts": (
            "Rollout loss rate", "Rollout pressure rate", "Lateral speed",
            "Overall loss rate", "Weight", "Penalty rate",
        ),
        "Stunt & twist": (
            "Switch-block loss rate", "Switch-block pressure rate",
            "Overall loss rate", "Penalty rate", "Weight",
        ),
        "Blitz pickup": (
            "Loss rate vs 5+ rushers",
            "Pressure rate vs 5+",
            "Sack rate vs 5+",
            "Weight",
            "Overall loss rate",
        ),
        "Long-developing": (
            "Long-play loss rate", "Long-play pressure rate",
            "Depth lost at 3s", "Sack rate", "Weight", "Penalty rate",
        ),
    }
    assert TACTIC_ATTRIBUTES == expected
    rendered = format_tactic_metrics(
        "Play-action",
        {"PA loss rate": "0.1", "PA pressure rate": "0.2"},
    )
    assert rendered.index("PA loss rate") < rendered.index("PA pressure rate")
    assert rendered.index("PA pressure rate") < rendered.index("Overall loss rate")


def test_reads_exact_player_fields_and_reports_unavailable_ones():
    data = pd.DataFrame(
        {
            "key": [7, 7, 8],
            "Loss_rate": [0.1, 0.1, 0.8],
            "Pressure rate": [None, None, 0.3],
            "weight": [320, 320, 300],
        }
    )

    values = tactic_metric_values(data, 7, "Traditional dropback")

    assert values["Loss rate"] == "0.1"
    assert values["Pressure rate"] == "Missing for this player"
    assert values["Weight"] == "320"
    assert values["Sack rate"] == "Not available in loaded data"


def test_reports_metrics_that_change_across_frames():
    data = pd.DataFrame({"key": [7, 7], "Lateral speed": [1.0, 2.0]})

    assert tactic_metric_values(data, 7, "Rollouts")["Lateral speed"] == "Varies by frame"


def test_player_options_are_unique_readable_and_exclude_ball():
    meta = pd.DataFrame(
        {
            "side": ["offense", "defense", "ball"],
            "displayName": ["Alex Smith", "Alex Smith", "Ball"],
            "jerseyNumber": [12, 4, None],
            "position": ["QB", "CB", "BALL"],
        },
        index=[10, 20, -1],
    )

    labels, by_label = player_options(meta)

    assert len(labels) == len(set(labels)) == 2
    assert set(by_label.values()) == {10, 20}
    assert all("Alex Smith" in label for label in labels)


def test_frame_status_includes_snap_relative_time_and_event():
    prepared = {
        "frames": [10, 11, 12],
        "snap_idx": 1,
        "events": {11: "ball_snap"},
    }

    assert frame_status(prepared, 1) == "Frame 11  ·  +0.0s from snap  ·  ball_snap"
    assert frame_status(prepared, 99) == "Frame 12  ·  +0.1s from snap"


def test_build_source_defaults_to_the_project_dataset():
    source = build_source()

    assert isinstance(source, RealSource)
    assert source.folder == Path(__file__).resolve().parents[1] / "data" / "raw"


def test_build_source_can_select_demo_mode():
    assert isinstance(build_source(demo=True), DemoSource)
