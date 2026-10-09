"""
Step 1: inspect the raw CSVs before any pipeline code is written.

Read-only. Prints file paths, row counts, whitelist column checks, the category
labels we need for config, and the centre snap-count distribution. It writes
nothing to disk.

Run from the project root:
    python -m backend.inspect_data
"""
from pathlib import Path

import pandas as pd

# Project-relative paths. These move into backend/config.py in Step 2.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
TRACKING_DIR = RAW_DATA_DIR / "tracking"

# The only columns the pipeline is allowed to read from each file.
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


def header(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def check_columns(path, wanted):
    """Read only the header row and report which whitelisted columns exist."""
    cols = list(pd.read_csv(path, nrows=0).columns)
    present = [c for c in wanted if c in cols]
    missing = [c for c in wanted if c not in cols]
    return present, missing


def load_whitelisted(name):
    path = RAW_DATA_DIR / name
    present, missing = check_columns(path, WHITELIST[name])
    df = pd.read_csv(path, usecols=present)
    print(f"{path.relative_to(PROJECT_ROOT)}  rows={len(df):,}")
    print(f"   present: {present}")
    print(f"   MISSING: {missing if missing else 'none'}")
    return df


def show_counts(series, label):
    print(f"\n{label}  ({series.nunique(dropna=False)} unique incl. NaN)")
    print(series.value_counts(dropna=False).to_string())


def main():
    # ------------------------------------------------------------------ files
    header("1. Files, row counts, whitelist columns")
    players = load_whitelisted("players.csv")
    plays = load_whitelisted("plays.csv")
    scout = load_whitelisted("pffScoutingData.csv")

    tracking_files = sorted(TRACKING_DIR.glob("tracking_*.csv"))
    print(f"\n{TRACKING_DIR.relative_to(PROJECT_ROOT)}  files={len(tracking_files)}")
    if tracking_files:
        present, missing = check_columns(tracking_files[0], WHITELIST["tracking"])
        print(f"   present (first file): {present}")
        print(f"   MISSING: {missing if missing else 'none'}")

    # --------------------------------------------------------- category labels
    header("2. Category labels")
    show_counts(plays["dropBackType"], "plays.dropBackType")
    show_counts(plays["pff_playAction"], "plays.pff_playAction")
    show_counts(scout["pff_role"], "scouting.pff_role")
    show_counts(scout["pff_positionLinedUp"], "scouting.pff_positionLinedUp")
    show_counts(scout["pff_blockType"], "scouting.pff_blockType (all rows)")

    # -------------------------------------------------------- pass-only check
    header("3. Is every play a dropback?")
    n_plays = len(plays)
    n_null = plays["dropBackType"].isna().sum()
    print(f"plays: {n_plays:,}   dropBackType blank: {n_null:,}")
    dup = plays.duplicated(["gameId", "playId"]).sum()
    print(f"duplicate (gameId, playId) in plays: {dup}")
    roles_per_play = scout.groupby(["gameId", "playId"])["pff_role"].apply(set)
    has_passer = roles_per_play.apply(lambda s: "Pass" in s).mean()
    print(f"share of scouted plays with a 'Pass' (passer) role: {has_passer:.1%}")

    # ---------------------------------------------------------- centre pool
    header("4. Centres: Pass Block snaps lined up at C")
    # Match labels case-insensitively here only, so a casing surprise is visible
    # rather than silently producing zero rows. Config will use exact labels.
    role_lbl = [r for r in scout["pff_role"].dropna().unique() if r.lower() == "pass block"]
    pos_lbl = [p for p in scout["pff_positionLinedUp"].dropna().unique() if p.upper() == "C"]
    print(f"exact role label matched: {role_lbl}   exact position label matched: {pos_lbl}")
    base = scout[scout["pff_role"].isin(role_lbl) & scout["pff_positionLinedUp"].isin(pos_lbl)]
    base = base.merge(plays, on=["gameId", "playId"], how="left", validate="many_to_one")
    print(f"base snaps (rows): {len(base):,}   unmatched to plays: {base['possessionTeam'].isna().sum()}")

    snaps = base.groupby("nflId").size().rename("base_snaps")
    snaps = snaps.to_frame().join(players.set_index("nflId")[["displayName", "weight"]])
    print(f"\nplayers who lined up at C on a Pass Block snap: {len(snaps)}")
    print("\nsnap-count distribution:")
    print(snaps["base_snaps"].describe().round(1).to_string())
    print("\nplayers at or above each threshold:")
    for t in [25, 50, 100, 150, 200, 250, 300]:
        print(f"   >= {t:>3}: {(snaps['base_snaps'] >= t).sum()}")
    print(f"\nnot found in players.csv: {snaps['displayName'].isna().sum()}")
    print("\nall centres, most snaps first:")
    print(snaps.sort_values("base_snaps", ascending=False).to_string())

    # Extra context needed to judge the tactic filters.
    show_counts(base["pff_blockType"], "\ncentre base snaps by pff_blockType")
    show_counts(base["dropBackType"], "\ncentre base snaps by dropBackType")
    flags = ["pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]
    print("\nblank allowed/beaten flags on centre base snaps:")
    print(base[flags].isna().sum().to_string())

    rushers = (scout["pff_role"] == "Pass Rush").groupby([scout["gameId"], scout["playId"]]).sum()
    base = base.merge(rushers.rename("n_rushers").reset_index(), on=["gameId", "playId"], how="left")
    show_counts(base["n_rushers"], "\ncentre base snaps by number of Pass Rush rows on the play")

    # Penalties: are centre fouls ever charged on plays outside his base snaps?
    foul_cols = ["foulNFLId1", "foulNFLId2", "foulNFLId3"]
    long_fouls = plays.melt(id_vars=["gameId", "playId"], value_vars=foul_cols,
                            value_name="nflId").dropna(subset=["nflId"])
    long_fouls["nflId"] = long_fouls["nflId"].astype("int64")
    centre_fouls = long_fouls[long_fouls["nflId"].isin(snaps.index)]
    keys = base[["gameId", "playId", "nflId"]].drop_duplicates()
    on_base = centre_fouls.merge(keys, on=["gameId", "playId", "nflId"], how="inner")
    print(f"\nfouls charged to these centres: {len(centre_fouls)}   "
          f"on their base snaps: {len(on_base)}   elsewhere: {len(centre_fouls) - len(on_base)}")

    # --------------------------------------------------------------- tracking
    header("5. Tracking")
    if not tracking_files:
        print("no tracking files found: tracking attributes and long_dev would be disabled")
        return
    centre_ids = set(snaps.index)
    base_keys = set(map(tuple, keys.to_numpy()))
    total_rows, events, directions, found = 0, {}, set(), set()
    frames_after_snap = []
    for f in tracking_files:
        t = pd.read_csv(f, usecols=["gameId", "playId", "nflId", "frameId",
                                    "playDirection", "event"])
        total_rows += len(t)
        directions |= set(t["playDirection"].dropna().unique())
        # Count each event once per play (it is repeated on every player's row).
        ev = t.dropna(subset=["event"]).drop_duplicates(["gameId", "playId", "event"])
        for e, n in ev["event"].value_counts().items():
            events[e] = events.get(e, 0) + n
        # Which centre base snaps have the centre's own rows in tracking?
        c = t[t["nflId"].isin(centre_ids)]
        found |= set(map(tuple, c[["gameId", "playId", "nflId"]]
                         .drop_duplicates().astype("int64").to_numpy())) & base_keys
        # Frames available after the snap on centre rows (needed for 20 / 30 frame windows).
        snap = c[c["event"] == "ball_snap"].groupby(["gameId", "playId", "nflId"])["frameId"].min()
        last = c.groupby(["gameId", "playId", "nflId"])["frameId"].max()
        frames_after_snap.append((last - snap).dropna())

    print(f"tracking rows (all files, whitelisted cols): {total_rows:,}")
    print(f"playDirection values: {sorted(directions)}")
    print("\nevent tags (count = number of plays carrying that tag):")
    print(pd.Series(events).sort_values(ascending=False).to_string())
    print(f"\ncentre base snaps: {len(base_keys):,}   with the centre's own tracking rows: "
          f"{len(found):,} ({len(found) / len(base_keys):.1%})")
    fas = pd.concat(frames_after_snap)
    print(f"\nframes after 'ball_snap' on centre rows (n={len(fas):,}):")
    print(fas.describe().round(1).to_string())
    print(f"   share with >= 20 frames: {(fas >= 20).mean():.1%}   >= 30 frames: {(fas >= 30).mean():.1%}")


if __name__ == "__main__":
    main()
