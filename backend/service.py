"""
Service layer: the functions the Flask API (api.py) and the CLI (cli.py) call.

  get_tactics()                    enabled tactics: key, name, description, attributeCount
  get_rankings(tactic_key, limit)  ranked centers for one tactic (the API's JSON contract)

Both return plain JSON-safe dicts/lists (no numpy types, no NaN). The processed
files are read once per process and cached; call reload() after re-running
`python -m backend.preprocess` in a running process.
"""
import functools
import json

import pandas as pd

from backend import config, scoring
from backend.formatting import display, json_safe
from backend.tactics import TACTICS, TARGET, TRACKING_ATTRIBUTES, active_attributes

# Integer columns that may be blank (read as nullable so they stay whole numbers).
STATS_DTYPES = {"nflId": "int64", "age": "Int64", "height_in": "Int64",
                "weight_lb": "Int64", "base_snaps": "int64"}


class ProcessedDataMissing(RuntimeError):
    """data/processed/ has not been built yet."""


class UnknownTactic(ValueError):
    """The tactic key does not exist, or is disabled (needs tracking that wasn't used)."""


class InvalidLimit(ValueError):
    """limit is not an integer from MIN_LIMIT to MAX_LIMIT."""


# ----------------------------------------------------------------------- loading
@functools.lru_cache(maxsize=1)
def load_processed():
    """(stats DataFrame, benchmark dict by attribute, meta dict), read once."""
    paths = [config.CENTERS_STATS_CSV, config.BENCHMARKS_JSON, config.META_JSON]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise ProcessedDataMissing(
            f"Processed data not found ({', '.join(missing)}). "
            "Run `python -m backend.preprocess` from the repo root.")
    stats = pd.read_csv(config.CENTERS_STATS_CSV, dtype=STATS_DTYPES)
    benchmarks = json.loads(config.BENCHMARKS_JSON.read_text(encoding="utf-8"))["attributes"]
    meta = json.loads(config.META_JSON.read_text(encoding="utf-8"))
    return stats, benchmarks, meta


def reload():
    """Forget the cached processed files so the next call re-reads them."""
    load_processed.cache_clear()


# ------------------------------------------------------------------- pure builders
def enabled_keys(meta):
    """Tactics that preprocess built (meta.json) and that tactics.py still defines."""
    return [key for key in meta["enabledTactics"] if key in TACTICS]


def list_tactics(meta):
    tracking = meta["trackingUsed"]
    return [{"key": key,
             "name": TACTICS[key]["name"],
             "description": TACTICS[key]["description"],
             "attributeCount": len(active_attributes(TACTICS[key], tracking))}
            for key in enabled_keys(meta)]


def check_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) \
            or not config.MIN_LIMIT <= limit <= config.MAX_LIMIT:
        raise InvalidLimit(f"limit must be a whole number from {config.MIN_LIMIT} "
                           f"to {config.MAX_LIMIT}, got {limit!r}")


def check_tactic(tactic_key, meta):
    if tactic_key in enabled_keys(meta):
        return
    if tactic_key in TACTICS:
        raise UnknownTactic(f"Tactic '{tactic_key}' needs tracking data, which was not "
                            "used when the processed files were built.")
    raise UnknownTactic(f"Unknown tactic '{tactic_key}'. Valid tactics: "
                        f"{', '.join(enabled_keys(meta))}.")


def _benchmark(attr, benchmarks):
    """(ideal, floor) shown with an attribute; a target attribute's ideal is its target."""
    if attr.better == TARGET:
        return attr.target, None
    bench = benchmarks.get(attr.key) or {}
    return bench.get("ideal"), bench.get("floor")


def _column(attr):
    column = {"key": attr.key, "label": attr.label, "weight": round(attr.weight, 6),
              "better": attr.better, "format": attr.format}
    if attr.better == TARGET:
        column["target"] = attr.target
    return column


def build_rankings(stats, benchmarks, meta, tactic_key, limit=config.DEFAULT_LIMIT):
    """Rankings for one tactic from already-loaded data (see get_rankings)."""
    check_tactic(tactic_key, meta)
    check_limit(limit)
    tactic = TACTICS[tactic_key]
    attrs = active_attributes(tactic, meta["trackingUsed"])
    ranked = scoring.score_tactic(stats, tactic, attrs, benchmarks).head(limit)
    rows = stats.loc[ranked.index]

    players = []
    for (_, r), (_, s) in zip(ranked.iterrows(), rows.iterrows()):
        attributes = {}
        for attr in attrs:
            ideal, floor = _benchmark(attr, benchmarks)
            attributes[attr.key] = {
                "value": s[attr.key],
                "display": display(s[attr.key], attr.format),
                "score": int(scoring.round_half_up(100 * r[f"score_{attr.key}"])),
                "ideal": ideal,
                "floor": floor,
            }
        players.append({
            "rank": r["rank"],
            "nflId": s["nflId"],
            "name": s["name"],
            "team": s["team"],
            "age": s["age"],
            "suitability": r["suitability"],
            "confidence": r["confidence"],
            "tacticSnaps": r["tactic_snaps"],
            "baseSnaps": r["base_snaps"],
            "attributes": attributes,
            "topStrength": r["top_strength"],
            "biggestConcern": r["biggest_concern"],
        })

    return json_safe({
        "tactic": tactic_key,
        "tacticName": tactic["name"],
        # True if this tactic's ranking used tracking: its filter or an attribute.
        "trackingUsed": bool(meta["trackingUsed"] and (
            tactic["requires_tracking"] or any(a.key in TRACKING_ATTRIBUTES for a in attrs))),
        "columns": [_column(a) for a in attrs],
        "players": players,
    })


# ----------------------------------------------------------------- public service
def get_tactics():
    _, _, meta = load_processed()
    return list_tactics(meta)


def get_rankings(tactic_key, limit=config.DEFAULT_LIMIT):
    stats, benchmarks, meta = load_processed()
    return build_rankings(stats, benchmarks, meta, tactic_key, limit)
