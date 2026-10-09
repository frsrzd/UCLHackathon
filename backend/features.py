"""
Per-snap flags and per-center stats, computed from the loader's trimmed DataFrames.

  rushers_per_play()  n_rushers per play = number of 'Pass Rush' rows on it
  base_snaps()        one row per center snap: 'Pass Block' role, lined up at C,
                      joined to its play and its n_rushers
  add_flags()         loss / pressure / sack / penalty as 0/1 on each snap
  qualifying_snaps()  only centers with at least MIN_BASE_SNAPS base snaps
  center_stats()      one row per qualifying center: profile, counts, shrunk
                      overall and tactic rates, tracking averages
  benchmarks()        ideal and floor per scored attribute, from percentiles

Shrinkage pulls small samples toward a prior so a few snaps can't produce an
extreme rate (rate = events / snaps before shrinking):
  overall rate = (events + K_OVERALL * league rate) / (base snaps + K_OVERALL)
  tactic rate  = (events + K_TACTIC * his shrunk overall rate) / (tactic snaps + K_TACTIC)
With 0 tactic snaps, a tactic rate therefore equals his shrunk overall rate.
"""
import numpy as np
import pandas as pd

from backend import config
from backend.tactics import LOWER, TARGET, TRACKING_ATTRIBUTES, active_attributes, tactic_mask

KEYS = ["gameId", "playId", "nflId"]
PLAY_KEYS = ["gameId", "playId"]

# Per-snap 0/1 outcomes -> the column name used for their counts.
COUNT_COLUMNS = {"loss": "losses", "pressure": "pressures", "sack": "sacks",
                 "penalty": "penalties"}
TACTIC_RATES = ["loss", "pressure", "sack"]     # computed for every tactic (no penalty)


# --------------------------------------------------------------------------- snaps
def rushers_per_play(scouting):
    """(gameId, playId, n_rushers) for every scouted play."""
    is_rusher = scouting["pff_role"].eq(config.PASS_RUSH_ROLE)
    counts = is_rusher.groupby([scouting["gameId"], scouting["playId"]]).sum()
    return counts.rename("n_rushers").astype("int64").reset_index()


def base_snaps(scouting, plays, n_rushers):
    """Scouting rows with pff_role == 'Pass Block' and pff_positionLinedUp == 'C',
    joined to plays on (gameId, playId), plus n_rushers."""
    is_base = (scouting["pff_role"].eq(config.PASS_BLOCK_ROLE)
               & scouting["pff_positionLinedUp"].eq(config.CENTER_POSITION))
    snaps = scouting.loc[is_base, KEYS + ["pff_blockType"] + config.LOSS_FLAGS]
    snaps = snaps.merge(plays, on=PLAY_KEYS, how="left", validate="many_to_one")
    return snaps.merge(n_rushers, on=PLAY_KEYS, how="left", validate="many_to_one")


def add_flags(snaps):
    """Add 0/1 columns per snap:
      loss     = beaten, hit, hurry or sack allowed
      pressure = hit, hurry or sack allowed
      sack     = sack allowed
      penalty  = his nflId is one of the play's foulNFLId1-3
    A blank allowed/beaten flag on a Pass Block row counts as 0."""
    snaps = snaps.copy()
    flags = snaps[config.LOSS_FLAGS].fillna(0).astype(bool)
    snaps["loss"] = flags[config.LOSS_FLAGS].any(axis=1).astype(int)
    snaps["pressure"] = flags[config.PRESSURE_FLAGS].any(axis=1).astype(int)
    snaps["sack"] = flags[config.SACK_FLAG].astype(int)
    fouls = snaps[config.FOUL_ID_COLUMNS].astype("Int64")       # blank -> <NA>, never equal
    snaps["penalty"] = (fouls.eq(snaps["nflId"], axis=0).fillna(False)
                        .any(axis=1).astype(int))
    return snaps


def qualifying_snaps(snaps, min_snaps=None):
    """Base snaps of centers with at least `min_snaps` (default MIN_BASE_SNAPS) of them."""
    min_snaps = config.MIN_BASE_SNAPS if min_snaps is None else min_snaps
    per_center = snaps.groupby("nflId")["nflId"].transform("size")
    return snaps[per_center >= min_snaps].copy()


# --------------------------------------------------------------------------- rates
def shrink(events, snaps, prior, k):
    """Shrunk rate = (events + k * prior) / (snaps + k). Works on numbers or Series."""
    return (events + k * prior) / (snaps + k)


def league_rates(snaps):
    """Pooled rate of each outcome across all qualifying centers' base snaps
    (total events / total snaps), the prior for the overall rates."""
    return {f"{kind}_rate": float(snaps[kind].mean()) for kind in COUNT_COLUMNS}


def age_on(birth_dates, as_of):
    """Whole years completed on `as_of`; a blank birth date gives <NA>."""
    as_of = pd.Timestamp(as_of)
    born = pd.to_datetime(birth_dates)
    birthday_ahead = ((born.dt.month > as_of.month)
                      | ((born.dt.month == as_of.month) & (born.dt.day > as_of.day)))
    return (as_of.year - born.dt.year - birthday_ahead.astype(int)).astype("Int64")


def center_profiles(snaps, players):
    """name, team, age, height_in, weight_lb and base_snaps per center (index nflId).
    Team is his most frequent possessionTeam on base snaps (ties: alphabetical)."""
    base = snaps.groupby("nflId").size().rename("base_snaps")
    per_team = snaps.groupby(["nflId", "possessionTeam"]).size().rename("n").reset_index()
    team = (per_team.sort_values(["nflId", "n", "possessionTeam"], ascending=[True, False, True])
            .drop_duplicates("nflId").set_index("nflId")["possessionTeam"])
    info = players.set_index("nflId").reindex(base.index)
    profile = pd.DataFrame({
        "name": info["displayName"],
        "team": team.reindex(base.index),
        "age": age_on(info["birthDate"], config.AGE_AS_OF),
        "height_in": info["height_in"],
        "weight_lb": info["weight"],
        "base_snaps": base,
    })
    profile.index.name = "nflId"
    return profile.sort_index()


def center_stats(snaps, players, tactics):
    """One row per qualifying center (index nflId). `snaps` are the qualifying base
    snaps with flags (and tracking columns if used); `tactics` the enabled ones.

    Columns: profile; overall counts (losses, pressures, sacks, penalties) and
    shrunk rates; then per tactic <prefix>_snaps, its counts and shrunk rates; and,
    after the tactic that uses it, each tracking attribute with <attr>_snaps."""
    stats = center_profiles(snaps, players)
    centers = stats.index

    # Overall: all base snaps, shrunk toward the league rate.
    league = league_rates(snaps)
    counts = snaps.groupby("nflId")[list(COUNT_COLUMNS)].sum().reindex(centers)
    for kind, count_col in COUNT_COLUMNS.items():
        stats[count_col] = counts[kind]
    for kind, count_col in COUNT_COLUMNS.items():
        stats[f"{kind}_rate"] = shrink(stats[count_col], stats["base_snaps"],
                                       league[f"{kind}_rate"], config.K_OVERALL)

    # Per tactic: the snaps its filter keeps, shrunk toward his own overall rate.
    for tactic in tactics.values():
        prefix = tactic["prefix"]
        kept = snaps[tactic_mask(tactic, snaps)]
        by_center = kept.groupby("nflId")
        n = by_center.size().reindex(centers, fill_value=0)
        stats[f"{prefix}_snaps"] = n
        for kind in TACTIC_RATES:
            events = by_center[kind].sum().reindex(centers, fill_value=0)
            stats[f"{prefix}_{COUNT_COLUMNS[kind]}"] = events
            stats[f"{prefix}_{kind}_rate"] = shrink(events, n, stats[f"{kind}_rate"],
                                                    config.K_TACTIC)

        # Tracking attributes: plain average over this tactic's snaps that have a value.
        for attr in tactic["attributes"]:
            if attr.key in TRACKING_ATTRIBUTES and attr.key in kept.columns:
                values = kept.dropna(subset=[attr.key]).groupby("nflId")[attr.key]
                stats[attr.key] = values.mean().reindex(centers)
                stats[f"{attr.key}_snaps"] = values.size().reindex(centers, fill_value=0)
    return stats


# ----------------------------------------------------------------------- benchmarks
def benchmarks(stats, tactics, tracking_used):
    """Ideal and floor for every scored attribute except target ones (whose ideal is
    the tactic's target), from the qualifying centers' values:
      lower is better:  ideal = LOW_PERCENTILE (10th),  floor = HIGH_PERCENTILE (90th)
      higher is better: ideal = HIGH_PERCENTILE (90th), floor = LOW_PERCENTILE (10th)
    Percentiles use numpy's default linear interpolation; blank values are skipped."""
    out = {}
    for tactic in tactics.values():
        for attr in active_attributes(tactic, tracking_used):
            if attr.better == TARGET or attr.key in out:
                continue
            values = stats[attr.key].dropna().astype(float)
            ideal = floor = None
            if len(values):
                low, high = np.percentile(values, [config.LOW_PERCENTILE,
                                                   config.HIGH_PERCENTILE])
                ideal, floor = (low, high) if attr.better == LOWER else (high, low)
            out[attr.key] = {"better": attr.better, "ideal": ideal, "floor": floor,
                             "centers": len(values)}
    return out
