"""
Print and export the top centers for one tactic, or for every enabled tactic.

    python -m backend.cli --tactic stunt_twist
    python -m backend.cli --all

Rankings come from service.get_rankings(), the same function the Flask API calls.
Each tactic is printed (rank, name, team, suit%, confidence, then every attribute's
display value in importance order) and written to outputs/<tactic>_top15.csv and
outputs/<tactic>_top15.json.
"""
import argparse
import json
import sys

import pandas as pd

from backend import config, service


def table(result):
    """Printable table: one row per player, attributes in importance order."""
    rows = []
    for p in result["players"]:
        row = {"Rank": p["rank"], "Name": p["name"], "Team": p["team"],
               "Suit%": f"{p['suitability']:.1f}", "Conf": p["confidence"]}
        for col in result["columns"]:
            row[col["label"]] = p["attributes"][col["key"]]["display"]
        rows.append(row)
    return pd.DataFrame(rows)


def flat_rows(result):
    """CSV rows: player fields, then value / display / score (0-100) per attribute."""
    rows = []
    for p in result["players"]:
        row = {k: p[k] for k in ["rank", "nflId", "name", "team", "age", "suitability",
                                 "confidence", "tacticSnaps", "baseSnaps"]}
        for col in result["columns"]:
            attr = p["attributes"][col["key"]]
            row[col["key"]] = attr["value"]
            row[f"{col['key']}_display"] = attr["display"]
            row[f"{col['key']}_score"] = attr["score"]
        row["topStrength"] = p["topStrength"]
        row["biggestConcern"] = p["biggestConcern"]
        rows.append(row)
    return pd.DataFrame(rows)


def export(result):
    """Write outputs/<tactic>_top<N>.csv and .json; return the two paths."""
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = config.OUTPUTS_DIR / f"{result['tactic']}_top{config.CLI_TOP_N}"
    csv_path, json_path = stem.with_suffix(".csv"), stem.with_suffix(".json")
    flat_rows(result).to_csv(csv_path, index=False, lineterminator="\n")
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    return csv_path, json_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank centers for pass-protection tactics.")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--tactic", help="tactic key, e.g. dropback")
    which.add_argument("--all", action="store_true", help="every enabled tactic")
    args = parser.parse_args(argv)

    try:
        keys = [t["key"] for t in service.get_tactics()] if args.all else [args.tactic]
        for key in keys:
            result = service.get_rankings(key, config.CLI_TOP_N)
            tracking = "yes" if result["trackingUsed"] else "no"
            print(f"\n{result['tacticName']} ({key}): top {len(result['players'])}, "
                  f"tracking used: {tracking}")
            print(table(result).to_string(index=False))
            for path in export(result):
                print(f"wrote {path.relative_to(config.PROJECT_ROOT)}")
    except (service.ProcessedDataMissing, service.UnknownTactic) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
