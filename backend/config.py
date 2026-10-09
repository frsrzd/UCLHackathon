"""
Backend configuration: every path, column list, label and tunable value lives here.

All paths are built from this file's own location, so the code runs from a fresh
clone on Windows, macOS or Linux without editing anything.
"""
from pathlib import Path

# ----------------------------------------------------------------------------- paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"          # read-only: never modified by code
TRACKING_DIR = RAW_DATA_DIR / "tracking"
TRACKING_PATTERN = "tracking_*.csv"                   # one file per game; optional
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"   # written by backend.preprocess
OUTPUTS_DIR = PROJECT_ROOT / "outputs"                # written by backend.cli

# ------------------------------------------------------------------ column whitelist
# The ONLY columns the backend may read from each file. data_loader.py passes these
# lists to pandas as usecols= and raises a clear error if any column is missing.
WHITELIST = {
    "players.csv": ["nflId", "displayName", "height", "weight", "birthDate"],
    "plays.csv": ["gameId", "playId", "possessionTeam", "pff_playAction",
                  "dropBackType", "foulNFLId1", "foulNFLId2", "foulNFLId3"],
    "pffScoutingData.csv": ["gameId", "playId", "nflId", "pff_role",
                            "pff_positionLinedUp", "pff_beatenByDefender",
                            "pff_hitAllowed", "pff_hurryAllowed",
                            "pff_sackAllowed", "pff_blockType"],
    "tracking": ["gameId", "playId", "nflId", "frameId", "x", "y",
                 "playDirection", "event"],
}
