import socket
from pathlib import Path

import pandas as pd
import pytest

from backend.formation_viewer import (
    TACTIC_KEYS,
    BackendUnavailable,
    DemoSource,
    RankingsClient,
    RealSource,
    build_source,
    format_player_ranking,
    format_top_ranking,
    frame_status,
    player_options,
    tactic_priorities,
)
from backend.tactics import TACTICS

# A trimmed /api/rankings response, shaped like backend/service.py builds it.
SAMPLE_RANKING = {
    "tactic": "stunt_twist",
    "tacticName": "Stunt & twist handling",
    "trackingUsed": False,
    "columns": [
        {"key": "sw_loss_rate", "label": "Switch-block loss rate", "weight": 0.6,
         "better": "lower", "format": "pct"},
        {"key": "weight_lb", "label": "Weight", "weight": 0.4, "better": "target",
         "format": "lb", "target": 305},
    ],
    "players": [
        {"rank": 1, "nflId": 53492, "name": "Creed Humphrey", "team": "KC", "age": None,
         "suitability": 97.0, "confidence": "Low", "tacticSnaps": 16, "baseSnaps": 339,
         "attributes": {
             "sw_loss_rate": {"value": 0.022, "display": "2.2%", "score": 100,
                              "ideal": 0.058, "floor": 0.198},
             "weight_lb": {"value": 316, "display": "316 lb", "score": 70,
                           "ideal": 305, "floor": None}},
         "topStrength": "sw_loss_rate", "biggestConcern": "weight_lb"},
        {"rank": 2, "nflId": 34472, "name": "Alex Mack", "team": "SF", "age": 35,
         "suitability": 94.7, "confidence": "Low", "tacticSnaps": 4, "baseSnaps": 218,
         "attributes": {
             "sw_loss_rate": {"value": 0.075, "display": "7.5%", "score": 88,
                              "ideal": 0.058, "floor": 0.198},
             "weight_lb": {"value": 311, "display": "311 lb", "score": 95,
                           "ideal": 305, "floor": None}},
         "topStrength": "sw_loss_rate", "biggestConcern": "sw_loss_rate"},
    ],
}


def test_tactic_choices_come_from_the_backend_in_priority_order():
    assert set(TACTIC_KEYS.values()) == set(TACTICS)
    assert TACTIC_KEYS["Play-action protection"] == "play_action"
    assert tactic_priorities("play_action") == [
        "PA loss rate", "PA pressure rate", "Overall loss rate",
        "PA sack rate", "Weight", "Penalty rate",
    ]


def test_top_ranking_lists_centers_in_rank_order():
    text = format_top_ranking(SAMPLE_RANKING, n=2)

    assert "Stunt & twist handling: top 2 centers" in text
    assert text.index(" 1. Creed Humphrey (KC)") < text.index(" 2. Alex Mack (SF)")
    assert "97.0%" in text and "94.7%" in text


def test_player_ranking_shows_rank_values_and_scores():
    text = format_player_ranking(SAMPLE_RANKING, 53492)

    assert "Rank 1 of 2" in text and "suitability 97.0%" in text
    assert "Switch-block loss rate: 2.2%  (score 100/100, weight 60%)" in text
    assert "Weight: 316 lb  (score 70/100, weight 40%)" in text
    assert "Biggest concern: Weight" in text


def test_unranked_players_are_reported_not_guessed():
    text = format_player_ranking(SAMPLE_RANKING, 99999)

    assert "Not ranked" in text and "150" in text


def test_client_explains_how_to_start_an_unreachable_backend():
    with socket.socket() as s:                      # a local port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    with pytest.raises(BackendUnavailable, match="python app.py"):
        RankingsClient(f"http://127.0.0.1:{port}", timeout=2).rankings("dropback")


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
