"""
Build the processed files the API serves, from the raw CSVs.

    python -m backend.preprocess                # uses tracking files if present
    python -m backend.preprocess --no-tracking  # ignore tracking (the fallback path)

Writes to data/processed/:
  centers_stats.csv  one row per qualifying center: profile, event counts, shrunk
                     overall and tactic rates, tracking averages (features.py)
  benchmarks.json    ideal / floor per scored attribute (features.benchmarks)
  meta.json          tracking used?, enabled tactics, row counts, league rates,
                     settings and a timestamp
"""
import argparse
import json
from datetime import datetime, timezone

from backend import config, data_loader, features, tracking_features
from backend.formatting import json_safe
from backend.tactics import enabled_tactics

KEYS = ["gameId", "playId", "nflId"]


def build(use_tracking=True):
    """Run the whole pipeline in memory. Returns (stats, benchmarks, meta)."""
    players = data_loader.load_players()
    plays = data_loader.load_plays()
    scouting = data_loader.load_scouting()

    snaps = features.base_snaps(scouting, plays, features.rushers_per_play(scouting))
    snaps = features.add_flags(snaps)
    qualified = features.qualifying_snaps(snaps)

    files = data_loader.tracking_files()
    tracking_used = use_tracking and bool(files)
    coverage = {}
    if tracking_used:
        per_snap, coverage = tracking_features.snap_features(
            data_loader.iter_tracking_chunks(files), qualified[KEYS])
        qualified = qualified.merge(per_snap, on=KEYS, how="left", validate="one_to_one")

    tactics = enabled_tactics(tracking_used)
    stats = features.center_stats(qualified, players, tactics)
    bench = {
        "method": (f"Percentiles across the {len(stats)} qualifying centers' values. "
                   f"Lower is better: ideal = {config.LOW_PERCENTILE}th percentile, "
                   f"floor = {config.HIGH_PERCENTILE}th. Higher is better: ideal = "
                   f"{config.HIGH_PERCENTILE}th, floor = {config.LOW_PERCENTILE}th. "
                   "Target attributes (weight) are scored against the tactic's target."),
        "attributes": features.benchmarks(stats, tactics, tracking_used),
    }
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trackingUsed": tracking_used,
        "trackingFilesFound": len(files),
        "enabledTactics": list(tactics),
        "rowCounts": {
            "players.csv": len(players),
            "plays.csv": len(plays),
            "pffScoutingData.csv": len(scouting),
            **coverage,
            "centerBaseSnaps": len(snaps),
            "centersWithBaseSnaps": snaps["nflId"].nunique(),
            "qualifyingCenters": len(stats),
            "qualifyingBaseSnaps": len(qualified),
        },
        "tacticSnaps": {key: stats[f"{t['prefix']}_snaps"].sum() for key, t in tactics.items()},
        "leagueRates": features.league_rates(qualified),
        "settings": {name: getattr(config, name) for name in [
            "MIN_BASE_SNAPS", "K_OVERALL", "K_TACTIC", "AGE_AS_OF", "BLITZ_MIN_RUSHERS",
            "LONG_DEV_MIN_SECONDS", "LOW_PERCENTILE", "HIGH_PERCENTILE",
            "FRAMES_PER_SECOND", "LATERAL_WINDOW_FRAMES", "DEPTH_WINDOW_FRAMES",
            "SNAP_EVENTS", "PASS_FORWARD_EVENTS", "SACK_EVENTS", "RUN_EVENTS"]},
    }
    return stats, bench, meta


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(json_safe(payload), f, indent=2, allow_nan=False)
        f.write("\n")


def write(stats, bench, meta):
    """Write the three processed files (LF line endings, so they diff cleanly)."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stats.reset_index().to_csv(config.CENTERS_STATS_CSV, index=False, lineterminator="\n")
    _write_json(config.BENCHMARKS_JSON, bench)
    _write_json(config.META_JSON, meta)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build data/processed/ from data/raw/.")
    parser.add_argument("--no-tracking", action="store_true",
                        help="ignore tracking files even if present")
    args = parser.parse_args(argv)

    stats, bench, meta = build(use_tracking=not args.no_tracking)
    write(stats, bench, meta)

    counts = meta["rowCounts"]
    print(f"qualifying centers: {counts['qualifyingCenters']} "
          f"(>= {config.MIN_BASE_SNAPS} base snaps), {counts['qualifyingBaseSnaps']:,} snaps")
    print(f"tracking used: {meta['trackingUsed']} "
          f"({meta['trackingFilesFound']} files found)")
    print(f"enabled tactics: {', '.join(meta['enabledTactics'])}")
    for path in (config.CENTERS_STATS_CSV, config.BENCHMARKS_JSON, config.META_JSON):
        print(f"wrote {path.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
