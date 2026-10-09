"""
Turn centers' stats into a ranked suitability % for one tactic.

Attribute score, 0 to 1, for a center's value x (ideal/floor from benchmarks.json):
  lower is better:  clip((floor - x) / (floor - ideal), 0, 1)
  higher is better: clip((x - floor) / (ideal - floor), 0, 1)
  target:           1 within +-5 lb of the target, falling linearly to 0 at +-25 lb
  ideal == floor, or the center has no value: 0.5 (neutral)

Suitability % = 100 x sum(weight x score) over the tactic's active attributes,
rounded half up to 1 decimal (unrounded scores are used in the sum).

Ranking: suitability descending; ties broken by tactic snaps, then base snaps
(more first), then nflId so the order is always the same.
  topStrength    = attribute with the largest weight x score
  biggestConcern = attribute with the largest weight x (1 - score)
  confidence     = High if tactic snaps >= 60, Medium if 25-59, Low if < 25
"""
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from backend import config
from backend.tactics import LOWER, TARGET


def round_half_up(x, digits=0):
    """Round like a person would (2.25 -> 2.3), not banker's rounding (2.25 -> 2.2)."""
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP))


def attribute_scores(values, attr, bench=None):
    """0-1 score for each value of one attribute (see the module docstring)."""
    x = pd.to_numeric(values, errors="coerce").astype(float)
    if attr.better == TARGET:
        full, zero = config.TARGET_FULL_SCORE_WITHIN, config.TARGET_ZERO_SCORE_AT
        distance = (x - attr.target).abs()
        score = ((zero - distance) / (zero - full)).clip(0, 1)
    else:
        ideal = (bench or {}).get("ideal")
        floor = (bench or {}).get("floor")
        if ideal is None or floor is None or ideal == floor:
            return pd.Series(config.NEUTRAL_SCORE, index=x.index)
        if attr.better == LOWER:
            score = ((floor - x) / (floor - ideal)).clip(0, 1)
        else:
            score = ((x - floor) / (ideal - floor)).clip(0, 1)
    return score.fillna(config.NEUTRAL_SCORE)


def confidence(tactic_snaps):
    if tactic_snaps >= config.CONFIDENCE_HIGH_MIN_SNAPS:
        return "High"
    if tactic_snaps >= config.CONFIDENCE_MEDIUM_MIN_SNAPS:
        return "Medium"
    return "Low"


def score_tactic(stats, tactic, attrs, benchmarks):
    """Score and rank every center in `stats` for `tactic`.

    attrs: the tactic's active attributes (tactics.active_attributes).
    Returns one row per center, best first, with: nflId, rank, suitability,
    confidence, tactic_snaps, base_snaps, top_strength, biggest_concern, and
    score_<attribute> (0-1) for each attribute."""
    scores = pd.DataFrame({a.key: attribute_scores(stats[a.key], a, benchmarks.get(a.key))
                           for a in attrs}, index=stats.index)
    weights = pd.Series({a.key: a.weight for a in attrs})
    weighted = scores * weights                        # weight x score, per attribute

    out = pd.DataFrame({
        "nflId": stats["nflId"],
        "suitability": (100 * weighted.sum(axis=1)).map(lambda v: round_half_up(v, 1)),
        "tactic_snaps": stats[f"{tactic['prefix']}_snaps"],
        "base_snaps": stats["base_snaps"],
        "top_strength": weighted.idxmax(axis=1),
        "biggest_concern": (weights - weighted).idxmax(axis=1),   # weight x (1 - score)
    }, index=stats.index)
    out["confidence"] = out["tactic_snaps"].map(confidence)
    out = out.join(scores.add_prefix("score_"))

    out = out.sort_values(["suitability", "tactic_snaps", "base_snaps", "nflId"],
                          ascending=[False, False, False, True])
    out.insert(1, "rank", range(1, len(out) + 1))
    return out
