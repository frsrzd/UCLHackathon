"""
Backend configuration: every path, column list, label and tunable value lives here.

All paths are built from this file's own location, so the code runs from a fresh
clone on Windows, macOS or Linux without editing anything. The tactic definitions
(filters, attributes, weights) live next door in tactics.py.
"""
from pathlib import Path

# ----------------------------------------------------------------------------- paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"          # read-only: never modified by code
PLAYERS_CSV = RAW_DATA_DIR / "players.csv"
PLAYS_CSV = RAW_DATA_DIR / "plays.csv"
SCOUTING_CSV = RAW_DATA_DIR / "pffScoutingData.csv"
TRACKING_DIR = RAW_DATA_DIR / "tracking"
TRACKING_PATTERN = "tracking_*.csv"                   # one file per game; optional

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"   # written by backend.preprocess
CENTERS_STATS_CSV = PROCESSED_DIR / "centers_stats.csv"
BENCHMARKS_JSON = PROCESSED_DIR / "benchmarks.json"
META_JSON = PROCESSED_DIR / "meta.json"

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

# -------------------------------------------------------------- reading the raw CSVs
NA_VALUES = ["NA", "None", ""]                # blanks in the raw files ('None' = no event)
BIRTHDATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y"]  # tried in order; a few players use the US form
TRACKING_CHUNK_ROWS = 500_000                 # tracking rows read at a time (bounds memory)

# ------------------------------------------------------------------- category labels
PASS_BLOCK_ROLE = "Pass Block"     # pff_role of a pass-blocking offensive player
PASS_RUSH_ROLE = "Pass Rush"       # pff_role counted for n_rushers
CENTER_POSITION = "C"              # pff_positionLinedUp of the center

TRADITIONAL_DROPBACK_TYPES = ["TRADITIONAL"]
DESIGNED_ROLLOUT_TYPES = ["DESIGNED_ROLLOUT_LEFT", "DESIGNED_ROLLOUT_RIGHT"]  # no scrambles

BLOCK_STANDARD = "PP"              # pff_blockType: standard pass protection
BLOCK_PLAY_ACTION = "PA"           # play-action pass protection
BLOCK_POCKET_ROLL = "PR"           # pocket roll (moving pocket)
BLOCK_SWITCH = "SW"                # switch block (stunts and twists)

PLAY_ACTION_YES = 1                # plays.pff_playAction
PLAY_ACTION_NO = 0

# -------------------------------------------------------------------- per-snap flags
BEATEN_FLAG = "pff_beatenByDefender"
HIT_FLAG = "pff_hitAllowed"
HURRY_FLAG = "pff_hurryAllowed"
SACK_FLAG = "pff_sackAllowed"
LOSS_FLAGS = [BEATEN_FLAG, HIT_FLAG, HURRY_FLAG, SACK_FLAG]   # loss = any of these
PRESSURE_FLAGS = [HIT_FLAG, HURRY_FLAG, SACK_FLAG]            # pressure = any of these
FOUL_ID_COLUMNS = ["foulNFLId1", "foulNFLId2", "foulNFLId3"]  # penalty = his nflId in any

# -------------------------------------------------------------------------- tracking
FRAMES_PER_SECOND = 10
# Event tags read from the center's own rows. Snap and pass-forward lists are in
# priority order: the manual tag is used when present, the automatic one only when
# the manual tag is missing (the auto tag usually fires a frame early).
SNAP_EVENTS = ["ball_snap", "autoevent_ballsnap"]
PASS_FORWARD_EVENTS = ["pass_forward", "autoevent_passforward"]
SACK_EVENTS = ["qb_sack", "qb_strip_sack"]
RUN_EVENTS = ["run"]               # QB run / scramble: ends the pocket like a throw or sack
LATERAL_WINDOW_FRAMES = 20         # lateral_speed: frames after the snap (2.0 s)
DEPTH_WINDOW_FRAMES = 30           # depth_lost_3s: frames after the snap (3.0 s)
PLAY_DIRECTION_SIGN = {"right": 1.0, "left": -1.0}  # right = offense attacks increasing x

# -------------------------------------------------------------- player pool and stats
MIN_BASE_SNAPS = 150               # base snaps needed to be ranked
K_OVERALL = 50                     # shrinkage strength for overall rates
K_TACTIC = 20                      # shrinkage strength for tactic rates
AGE_AS_OF = "2021-09-01"           # ages are whole years on this date (2021 season start)

BLITZ_MIN_RUSHERS = 5              # blitz tactic: snaps with at least this many rushers
LONG_DEV_MIN_SECONDS = 3.0         # long_dev tactic: snaps where time_to_event >= this

# ------------------------------------------------------------------------ benchmarks
LOW_PERCENTILE = 10                # ideal if lower is better, floor if higher is better
HIGH_PERCENTILE = 90               # floor if lower is better, ideal if higher is better

# --------------------------------------------------------------------------- scoring
TARGET_FULL_SCORE_WITHIN = 5       # target attribute: score 1 within +-5 (lb) of the target,
TARGET_ZERO_SCORE_AT = 25          # falling linearly to 0 at +-25 (lb)
NEUTRAL_SCORE = 0.5                # when ideal == floor, or a center has no value
CONFIDENCE_HIGH_MIN_SNAPS = 60     # tactic snaps: High >= 60, Medium 25-59, Low < 25
CONFIDENCE_MEDIUM_MIN_SNAPS = 25

# ------------------------------------------------------------------ rankings output
DEFAULT_LIMIT = 15                 # players returned when no limit is given
MIN_LIMIT = 1
MAX_LIMIT = 50
CLI_TOP_N = 15                     # rows the CLI prints and exports per tactic

# ---------------------------------------------------------------- local web server
API_HOST = "127.0.0.1"
API_PORT = 5001                    # not 5000: recent Macs reserve it for AirPlay Receiver
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173",    # Vite dev server
                "http://localhost:4173", "http://127.0.0.1:4173"]    # vite preview
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"   # app.py serves the built UI if present
