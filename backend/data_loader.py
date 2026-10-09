"""
The only pipeline module that reads the raw CSVs.

Every file is read with usecols= set to its list in config.WHITELIST, after a
header-only check that each whitelisted column exists (MissingColumnsError if not).
Types are fixed here, so the rest of the backend receives trimmed, typed DataFrames:

  load_players()          nflId, displayName, height_in, weight, birthDate (datetime)
  load_plays()            gameId, playId, possessionTeam, pff_playAction,
                          dropBackType, foulNFLId1-3 (nullable integers)
  load_scouting()         gameId, playId, nflId, pff_role, pff_positionLinedUp,
                          pff_blockType and the four allowed/beaten flags
  tracking_files()        the tracking CSVs present (none is fine)
  iter_tracking_chunks()  whitelisted tracking rows, file by file, chunk by chunk

Nothing here writes to data/raw.
"""
from pathlib import Path

import pandas as pd

from backend import config

PLAYERS_DTYPES = {"nflId": "int64", "weight": "float64"}
PLAYS_DTYPES = {"gameId": "int64", "playId": "int64", "pff_playAction": "Int64",
                **{col: "float64" for col in config.FOUL_ID_COLUMNS}}
SCOUTING_DTYPES = {"gameId": "int64", "playId": "int64", "nflId": "int64",
                   **{col: "float64" for col in config.LOSS_FLAGS}}   # all four flags
TRACKING_DTYPES = {"gameId": "int64", "playId": "int64", "nflId": "float64",  # blank = ball
                   "frameId": "int64", "x": "float64", "y": "float64"}


class MissingColumnsError(ValueError):
    """A raw CSV lacks one or more of its whitelisted columns."""


def check_columns(path, whitelist_key):
    """Read only the header row; raise if any whitelisted column is missing.
    Returns the whitelisted column list, ready for usecols=."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found (raw CSVs belong in data/raw/)")
    wanted = config.WHITELIST[whitelist_key]
    found = list(pd.read_csv(path, nrows=0).columns)
    missing = [col for col in wanted if col not in found]
    if missing:
        raise MissingColumnsError(
            f"{path.name} is missing whitelisted column(s) {missing}. "
            f"Expected all of {wanted}; the file has {found}.")
    return wanted


def _read(path, whitelist_key, dtype, **kwargs):
    usecols = check_columns(path, whitelist_key)
    return pd.read_csv(path, usecols=usecols, dtype=dtype,
                       na_values=config.NA_VALUES, **kwargs)


# --------------------------------------------------------------------------- players
def height_to_inches(height):
    """'6-3' (feet-inches) -> 75. A plain number is taken as inches already."""
    text = height.astype("string").str.strip()
    feet_inches = text.str.extract(r"^(\d+)-(\d+)$")
    inches = pd.to_numeric(feet_inches[0]) * 12 + pd.to_numeric(feet_inches[1])
    return inches.fillna(pd.to_numeric(text, errors="coerce")).astype("Int64")


def parse_birth_dates(text):
    """Parse each date with the first format in config.BIRTHDATE_FORMATS that fits;
    blank or unparseable dates become NaT."""
    formats = config.BIRTHDATE_FORMATS
    parsed = pd.to_datetime(text, format=formats[0], errors="coerce")
    for fmt in formats[1:]:
        parsed = parsed.fillna(pd.to_datetime(text, format=fmt, errors="coerce"))
    return parsed


def load_players(path=None):
    df = _read(path or config.PLAYERS_CSV, "players.csv", PLAYERS_DTYPES)
    df["height_in"] = height_to_inches(df.pop("height"))
    df["weight"] = df["weight"].round().astype("Int64")
    df["birthDate"] = parse_birth_dates(df["birthDate"])
    return df.drop_duplicates("nflId")


# ----------------------------------------------------------------- plays and scouting
def load_plays(path=None):
    df = _read(path or config.PLAYS_CSV, "plays.csv", PLAYS_DTYPES)
    for col in config.FOUL_ID_COLUMNS:
        df[col] = df[col].astype("Int64")       # 46090.0 -> 46090, blank -> <NA>
    return df


def load_scouting(path=None):
    # Allowed/beaten flags stay float with blanks here; features.add_flags fills them.
    return _read(path or config.SCOUTING_CSV, "pffScoutingData.csv", SCOUTING_DTYPES)


# -------------------------------------------------------------------------- tracking
def tracking_files(directory=None):
    """Sorted tracking CSVs in `directory` (default config.TRACKING_DIR); [] if none."""
    directory = Path(directory or config.TRACKING_DIR)
    return sorted(directory.glob(config.TRACKING_PATTERN)) if directory.is_dir() else []


def iter_tracking_chunks(files, chunk_rows=None):
    """Yield whitelisted rows of each tracking file in chunks of `chunk_rows`, so
    callers can filter as they go instead of holding every file in memory."""
    for path in files:
        reader = _read(path, "tracking", TRACKING_DTYPES,
                       chunksize=chunk_rows or config.TRACKING_CHUNK_ROWS)
        with reader:
            yield from reader
