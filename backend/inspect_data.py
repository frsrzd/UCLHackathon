"""
Step 1: inspect the raw CSVs before any pipeline code is written.

Read-only diagnostics. Loads only the whitelisted columns from backend/config.py
and writes nothing to disk. It prints:

  1. each file's path, size and row count, and which whitelisted columns are
     present or missing
  2. the category labels config.py needs (dropBackType, pff_playAction,
     pff_blockType, pff_role, pff_positionLinedUp) and the player field formats
  3. how many players lined up at C on Pass Block snaps, and their snap counts
  4. the fields the tactic filters use, measured on those centre snaps
  5. tracking (if present): event tags, and which snap / pass / sack events the
     centre's own rows carry on his base snaps

Unlike data_loader.py, this script reads each header first so it can REPORT a
missing column instead of stopping on it. Labels are matched case-insensitively
here only, so a casing surprise shows up rather than silently matching nothing;
the pipeline uses the exact labels set in config.py.

Run from the repo root:
    python -m backend.inspect_data
"""
from collections import Counter
from itertools import combinations

import pandas as pd

from backend import config

MB = 1024 * 1024
GITHUB_WARN_MB = 50          # GitHub warns above 50 MB and rejects files above 100 MB
KEYS = ["gameId", "playId", "nflId"]


def header(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def rel(path):
    """Path relative to the repo root, for printing."""
    return path.relative_to(config.PROJECT_ROOT)


def split_columns(path, wanted):
    """Read only the header row; return (present, missing) whitelisted columns."""
    cols = set(pd.read_csv(path, nrows=0).columns)
    return [c for c in wanted if c in cols], [c for c in wanted if c not in cols]


def load_whitelisted(name):
    """Load one top-level CSV, keeping only the whitelisted columns that exist."""
    path = config.RAW_DATA_DIR / name
    present, missing = split_columns(path, config.WHITELIST[name])
    df = pd.read_csv(path, usecols=present)
    print(f"{rel(path)}   size={path.stat().st_size / MB:.1f} MB   rows={len(df):,}")
    print(f"   present: {present}")
    print(f"   MISSING: {missing or 'none'}")
    return df


def show_counts(series, label):
    print(f"\n{label}  ({series.nunique(dropna=False)} unique incl. blank)")
    print(series.value_counts(dropna=False).to_string())


def main():
    # ------------------------------------------------------------------ 1. files
    header("1. Files: path, size, rows, whitelisted columns")
    players = load_whitelisted("players.csv")
    plays = load_whitelisted("plays.csv")
    scout = load_whitelisted("pffScoutingData.csv")

    tracking_files = sorted(config.TRACKING_DIR.glob(config.TRACKING_PATTERN))
    print(f"\n{rel(config.TRACKING_DIR)}   files={len(tracking_files)}")
    if tracking_files:
        sizes = [f.stat().st_size / MB for f in tracking_files]
        print(f"   size total={sum(sizes):.1f} MB   per file min={min(sizes):.1f} MB"
              f"  max={max(sizes):.1f} MB")
        bad = {f.name: missing for f in tracking_files
               if (missing := split_columns(f, config.WHITELIST["tracking"])[1])}
        print(f"   headers checked: {len(tracking_files)}   "
              f"files missing a whitelisted column: {len(bad)}")
        for name, missing in bad.items():
            print(f"      {name}: {missing}")
        print("   rows: counted in section 5 (one pass over every file)")

    big = [p for p in config.RAW_DATA_DIR.rglob("*")
           if p.is_file() and p.stat().st_size > GITHUB_WARN_MB * MB]
    print(f"\nraw files over {GITHUB_WARN_MB} MB: "
          f"{[f'{rel(p)} ({p.stat().st_size / MB:.0f} MB)' for p in big] or 'none'}")

    # --------------------------------------------------------- 2. category labels
    header("2. Category labels and player field formats")
    show_counts(plays["dropBackType"], "plays.dropBackType")
    show_counts(plays["pff_playAction"], "plays.pff_playAction")
    show_counts(scout["pff_role"], "scouting.pff_role")
    show_counts(scout["pff_blockType"], "scouting.pff_blockType (all rows)")
    show_counts(scout["pff_positionLinedUp"], "scouting.pff_positionLinedUp")

    height = players["height"].astype("string")
    feet_inches = height.str.fullmatch(r"\d+-\d+").fillna(False)
    plain_number = height.str.fullmatch(r"\d+").fillna(False)
    print(f"\nplayers.height   'F-I' text: {feet_inches.sum():,}   plain number: "
          f"{plain_number.sum():,}   other/blank: {(~(feet_inches | plain_number)).sum():,}"
          f"   e.g. {height.dropna().head(3).tolist()}")
    born = pd.to_datetime(players["birthDate"], format="%Y-%m-%d", errors="coerce")
    odd = players.loc[born.isna() & players["birthDate"].notna(), "birthDate"]
    print(f"players.birthDate   parsed as YYYY-MM-DD: {born.notna().sum():,}   blank: "
          f"{players['birthDate'].isna().sum():,}   other format: {len(odd):,}"
          f"   e.g. {odd.head(3).tolist()}")
    print(f"players.weight   blank: {players['weight'].isna().sum():,}")

    # ------------------------------------------------------------ 3. centre pool
    header("3. Centres: Pass Block snaps lined up at C")
    roles = scout["pff_role"].dropna().unique()
    role_lbl = [r for r in roles if r.lower() == "pass block"]
    rush_lbl = [r for r in roles if r.lower() == "pass rush"]
    pos_lbl = [p for p in scout["pff_positionLinedUp"].dropna().unique() if p.upper() == "C"]
    print(f"labels matched   role: {role_lbl}   rusher role: {rush_lbl}   position: {pos_lbl}")

    base = scout[scout["pff_role"].isin(role_lbl) & scout["pff_positionLinedUp"].isin(pos_lbl)]
    base = base.merge(plays, on=["gameId", "playId"], how="left", validate="many_to_one")
    print(f"base snaps (rows): {len(base):,}   unmatched to plays: "
          f"{base['possessionTeam'].isna().sum()}   plays with more than one: "
          f"{base.duplicated(['gameId', 'playId']).sum()}")

    snaps = base.groupby("nflId").size().rename("base_snaps").to_frame()
    snaps = snaps.join(players.set_index("nflId")[["displayName", "weight", "birthDate"]])
    teams = base.groupby("nflId")["possessionTeam"].nunique()
    print(f"\nplayers who lined up at C on a Pass Block snap: {len(snaps)}"
          f"   (not in players.csv: {snaps['displayName'].isna().sum()};"
          f" with more than one possessionTeam: {(teams > 1).sum()})")
    print("\nsnap-count distribution:")
    print(snaps["base_snaps"].describe().round(1).to_string())
    print("\nplayers at or above each snap count:")
    for t in [25, 50, 100, 150, 200, 250, 300]:
        print(f"   >= {t:>3}: {(snaps['base_snaps'] >= t).sum()}")
    print("\nall centres, most snaps first:")
    print(snaps.sort_values("base_snaps", ascending=False).to_string())

    # ------------------------------------------------- 4. tactic-filter fields
    header("4. Fields the tactic filters use, on centre base snaps")
    show_counts(base["pff_blockType"], "pff_blockType")
    show_counts(base["dropBackType"], "dropBackType")
    print("\npff_blockType x pff_playAction:")
    print(pd.crosstab(base["pff_blockType"].fillna("(blank)"), base["pff_playAction"],
                      margins=True).to_string())

    flags = ["pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]
    print("\nblank allowed/beaten flags:")
    print(base[flags].isna().sum().to_string())
    print("\nflag values:")
    print(base[flags].apply(lambda s: s.value_counts(dropna=False)).fillna(0)
          .astype(int).to_string())

    rushers = scout["pff_role"].isin(rush_lbl).groupby([scout["gameId"], scout["playId"]]).sum()
    base = base.merge(rushers.rename("n_rushers").reset_index(), on=["gameId", "playId"],
                      how="left")
    show_counts(base["n_rushers"], "\nnumber of Pass Rush rows on the play")

    # Penalties: compare foulNFLId* (float, often blank) to the centre's nflId.
    foul_cols = ["foulNFLId1", "foulNFLId2", "foulNFLId3"]
    fouls = (plays.melt(id_vars=["gameId", "playId"], value_vars=foul_cols, value_name="nflId")
             .dropna(subset=["nflId"]).astype({"nflId": "int64"}))
    centre_fouls = fouls[fouls["nflId"].isin(snaps.index)]
    keys = base[KEYS].drop_duplicates()
    on_base = centre_fouls.merge(keys, on=KEYS, how="inner")
    print(f"\nfouls charged to these centres: {len(centre_fouls)}   on their base snaps: "
          f"{len(on_base)}   on other plays: {len(centre_fouls) - len(on_base)}")

    # --------------------------------------------------------------- 5. tracking
    header("5. Tracking")
    if not tracking_files:
        print("no tracking files: tracking attributes and the long_dev tactic would be disabled")
        return

    total_rows, directions, play_events, dup_rows = 0, set(), Counter(), 0
    spans, first_frames = [], []
    for f in tracking_files:
        t = pd.read_csv(f, usecols=["gameId", "playId", "nflId", "frameId",
                                    "playDirection", "event"])
        total_rows += len(t)
        directions |= set(t["playDirection"].dropna().unique())
        # Count each event once per play (it repeats on every player's row in that frame).
        ev = t.dropna(subset=["event"]).drop_duplicates(["gameId", "playId", "event"])
        play_events.update(ev["event"].value_counts().to_dict())
        # The centre's own rows on his base snaps (ball rows have a blank nflId).
        c = t.dropna(subset=["nflId"]).astype({"nflId": "int64"}).merge(keys, on=KEYS)
        dup_rows += c.duplicated(KEYS + ["frameId"]).sum()
        spans.append(c.groupby(KEYS)["frameId"].agg(["min", "max"]))
        first_frames.append(c.dropna(subset=["event"])
                            .groupby(KEYS + ["event"])["frameId"].min())

    print(f"tracking rows (all files): {total_rows:,}")
    print(f"playDirection values: {sorted(directions)}")
    print("\nevent tags (count = plays carrying the tag on any row):")
    print(pd.Series(play_events).sort_values(ascending=False).to_string())

    span = pd.concat(spans)
    print(f"\ncentre base snaps: {len(keys):,}   with the centre's own tracking rows: "
          f"{len(span):,} ({len(span) / len(keys):.1%})   duplicate frame rows: {dup_rows}")

    # One row per base snap, one column per event: the first frame the centre's rows carry it.
    first = pd.concat(first_frames).unstack("event").reindex(span.index)
    print("\nevents on the centre's own rows (count = his base snaps carrying the tag):")
    print(first.notna().sum().sort_values(ascending=False).to_string())

    no_frame = pd.Series(index=first.index, dtype="float64")   # used when a tag never occurs

    def matching(needle):
        """Event names containing `needle` once underscores are dropped; manual tags
        sort before the automatic 'autoevent_*' tags."""
        names = [e for e in first.columns if needle in e.replace("_", "")]
        return sorted(names, key=lambda e: (e.startswith("autoevent"), e))

    def preferred_frame(names):
        """Frame of the first tag present on each snap, in `names` order."""
        return first[names].bfill(axis=1).iloc[:, 0] if names else no_frame

    # Candidate names for the snap, pass-forward and sack events.
    groups = {"snap": matching("ballsnap"), "pass forward": matching("passforward"),
              "sack": matching("sack")}
    for label, names in groups.items():
        print(f"\n[{label}] candidate events: {names}   combinations on base snaps:")
        present = first[names].notna()
        combo = present.apply(lambda r: " + ".join(n for n in names if r[n]) or "(none)", axis=1)
        print(combo.value_counts().to_string())
        for a, b in combinations(names, 2):
            both = first[[a, b]].dropna()
            if len(both):
                gap = both[b] - both[a]
                print(f"   frame gap {b} - {a} when both present (n={len(both):,}): "
                      f"min={gap.min():.0f}  median={gap.median():.0f}  max={gap.max():.0f}")

    end_names = groups["pass forward"] + groups["sack"]
    no_end = first[first[end_names].isna().all(axis=1)]
    other = no_end.drop(columns=end_names).notna().sum()
    print(f"\nbase snaps with no pass-forward or sack tag: {len(no_end):,}; "
          "other tags on those snaps:")
    print(other[other > 0].sort_values(ascending=False).to_string())

    # Frames and seconds after the snap, preferring the manual snap tag over the auto one.
    fps = 10                                     # tracking is recorded at 10 frames/second
    snap_frame = preferred_frame(groups["snap"])
    after = (span["max"] - snap_frame).dropna()
    print(f"\nframes recorded after the snap (n={len(after):,}):")
    print(after.describe().round(1).to_string())
    print(f"   share with >= 20 frames: {(after >= 20).mean():.1%}   "
          f">= 30 frames: {(after >= 30).mean():.1%}")

    pass_frame = preferred_frame(groups["pass forward"])
    sack_frame = first[groups["sack"]].min(axis=1)
    run_frame = first["run"] if "run" in first.columns else no_frame
    end_options = {
        "pass forward or sack": pd.concat([pass_frame, sack_frame], axis=1).min(axis=1),
        "pass forward, sack or run": pd.concat([pass_frame, sack_frame, run_frame],
                                               axis=1).min(axis=1),
    }
    for label, end_frame in end_options.items():
        secs = ((end_frame - snap_frame) / fps).dropna()
        print(f"\nseconds from snap to first '{label}' tag (n={len(secs):,}):")
        print(secs.describe().round(2).to_string())
        print("   snaps at or above:  " + "   ".join(
            f">= {s:.1f}s: {(secs >= s).sum():,}" for s in [2.5, 3.0, 3.5]))

    # Is a snap with no pass-forward or sack tag (mostly QB runs) more often a pressure?
    allowed = base.set_index(KEYS)[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]]
    pressure = allowed.fillna(0).max(axis=1).reindex(first.index)
    end_kind = pd.Series("no tag", index=first.index)
    end_kind[run_frame.notna()] = "run tag only"
    end_kind[sack_frame.notna()] = "sack tag"
    end_kind[pass_frame.notna()] = "pass-forward tag"
    print("\ncentre pressure allowed (hit/hurry/sack), by how the snap's tagging ends:")
    print(pressure.groupby(end_kind).agg(snaps="size", pressure_share="mean")
          .round(3).to_string())


if __name__ == "__main__":
    main()
