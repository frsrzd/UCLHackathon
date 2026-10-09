import pandas as pd
import pytest

from backend import data_loader


def write_csv(path, columns, rows):
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


PLAYS_COLUMNS = ["gameId", "playId", "possessionTeam", "pff_playAction", "dropBackType",
                 "foulNFLId1", "foulNFLId2", "foulNFLId3"]


def test_missing_whitelisted_column_raises_a_clear_error(tmp_path):
    columns = [c for c in PLAYS_COLUMNS if c != "dropBackType"]
    path = write_csv(tmp_path / "plays.csv", columns, [[1, 1, "KC", 0, None, None, None]])

    with pytest.raises(data_loader.MissingColumnsError, match=r"plays\.csv.*'dropBackType'"):
        data_loader.load_plays(path)


def test_only_whitelisted_columns_are_loaded(tmp_path):
    columns = PLAYS_COLUMNS + ["playDescription", "quarter"]   # not on the whitelist
    path = write_csv(tmp_path / "plays.csv", columns,
                     [[1, 7, "KC", 1, "TRADITIONAL", 46090.0, None, None, "pass", 1]])
    plays = data_loader.load_plays(path)

    assert list(plays.columns) == PLAYS_COLUMNS
    assert plays.loc[0, "foulNFLId1"] == 46090                 # float id -> whole number
    assert pd.isna(plays.loc[0, "foulNFLId2"])


def test_players_height_and_both_birth_date_formats(tmp_path):
    path = write_csv(tmp_path / "players.csv",
                     ["nflId", "displayName", "height", "weight", "birthDate", "collegeName"],
                     [[1, "A", "6-3", 300, "1995-09-02", "X"],
                      [2, "B", "6-5", 310, "05/15/1986", "Y"],
                      [3, "C", "75", 305, None, "Z"]])
    players = data_loader.load_players(path)

    assert list(players["height_in"]) == [75, 77, 75]
    assert list(players["birthDate"].dt.year[:2]) == [1995, 1986]
    assert pd.isna(players.loc[2, "birthDate"])
    assert "collegeName" not in players.columns


def test_no_tracking_folder_means_no_tracking_files(tmp_path):
    assert data_loader.tracking_files(tmp_path / "does_not_exist") == []
