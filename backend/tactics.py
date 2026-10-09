"""
The pass-protection tactics a center can be ranked for.

Each entry in TACTICS has:
  key, name, description   what the API shows
  prefix                   names this tactic's stat columns, e.g. "pa" -> pa_loss_rate
  filter                   function(snaps) -> boolean mask of the snaps that count
  requires_tracking        True if the tactic cannot exist without tracking data
  attributes               in importance order, as (key, label, weight, better, format):
      weight   fraction of the suitability score; a tactic's weights sum to 1
      better   "lower" or "higher" is better, or "target": closest to `target` is best
      format   how formatting.py displays the value: pct, lb, speed or yd

features.py computes <prefix>_loss_rate, <prefix>_pressure_rate and <prefix>_sack_rate
for every tactic. Tracking attributes are averaged over the snaps of the one tactic
that uses them. Without tracking, tracking attributes are dropped and the remaining
weights rescaled (active_attributes), and requires_tracking tactics are disabled
(enabled_tactics).
"""
from typing import NamedTuple, Optional

from backend import config

LOWER, HIGHER, TARGET = "lower", "higher", "target"
FORMATS = ("pct", "lb", "speed", "yd")

# Attributes that come from tracking data (see tracking_features.py).
TRACKING_ATTRIBUTES = {"lateral_speed", "depth_lost_3s"}


class Attribute(NamedTuple):
    key: str
    label: str
    weight: float
    better: str
    format: str
    target: Optional[float] = None   # only for better == "target"


# --------------------------------------------------------------------------- filters
# Each takes the per-snap DataFrame (base snaps of qualifying centers) and returns a
# boolean Series. A blank field never matches (tactic_mask turns NA into False).

def _dropback(s):
    return (s["pff_blockType"].eq(config.BLOCK_STANDARD)
            & s["pff_playAction"].eq(config.PLAY_ACTION_NO)
            & s["dropBackType"].isin(config.TRADITIONAL_DROPBACK_TYPES))


def _play_action(s):
    return s["pff_playAction"].eq(config.PLAY_ACTION_YES)


def _rollout(s):
    return (s["pff_blockType"].eq(config.BLOCK_POCKET_ROLL)
            | s["dropBackType"].isin(config.DESIGNED_ROLLOUT_TYPES))


def _stunt_twist(s):
    return s["pff_blockType"].eq(config.BLOCK_SWITCH)


def _blitz(s):
    return s["n_rushers"] >= config.BLITZ_MIN_RUSHERS


def _long_dev(s):
    return s["time_to_event"] >= config.LONG_DEV_MIN_SECONDS


# -------------------------------------------------------------------------- tactics
TACTICS = {
    "dropback": {
        "key": "dropback",
        "name": "Traditional dropback",
        "description": "Straight dropback protection: standard pass-pro blocks "
                       f"({config.BLOCK_STANDARD}) on traditional dropbacks with no "
                       "play-action fake.",
        "prefix": "dropback",
        "filter": _dropback,
        "requires_tracking": False,
        "attributes": [
            Attribute("dropback_loss_rate", "Loss rate", 0.35, LOWER, "pct"),
            Attribute("dropback_pressure_rate", "Pressure rate", 0.25, LOWER, "pct"),
            Attribute("dropback_sack_rate", "Sack rate", 0.15, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.15, TARGET, "lb", target=310),
            Attribute("penalty_rate", "Penalty rate", 0.10, LOWER, "pct"),
        ],
    },
    "play_action": {
        "key": "play_action",
        "name": "Play-action protection",
        "description": "Selling the run fake, then converting to pass protection, on "
                       "every play-action snap.",
        "prefix": "pa",
        "filter": _play_action,
        "requires_tracking": False,
        "attributes": [
            Attribute("pa_loss_rate", "PA loss rate", 0.35, LOWER, "pct"),
            Attribute("pa_pressure_rate", "PA pressure rate", 0.25, LOWER, "pct"),
            Attribute("loss_rate", "Overall loss rate", 0.15, LOWER, "pct"),
            Attribute("pa_sack_rate", "PA sack rate", 0.10, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.10, TARGET, "lb", target=305),
            Attribute("penalty_rate", "Penalty rate", 0.05, LOWER, "pct"),
        ],
    },
    "rollout": {
        "key": "rollout",
        "name": "Moving pocket / rollouts",
        "description": f"Pocket-roll blocks ({config.BLOCK_POCKET_ROLL}) and designed "
                       "rollouts, where the center has to move laterally with the "
                       "quarterback.",
        "prefix": "rollout",
        "filter": _rollout,
        "requires_tracking": False,
        "attributes": [
            Attribute("rollout_loss_rate", "Rollout loss rate", 0.35, LOWER, "pct"),
            Attribute("rollout_pressure_rate", "Rollout pressure rate", 0.20, LOWER, "pct"),
            Attribute("lateral_speed", "Lateral speed (tracking)", 0.20, HIGHER, "speed"),
            Attribute("loss_rate", "Overall loss rate", 0.10, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.10, TARGET, "lb", target=300),
            Attribute("penalty_rate", "Penalty rate", 0.05, LOWER, "pct"),
        ],
    },
    "stunt_twist": {
        "key": "stunt_twist",
        "name": "Stunt & twist handling",
        "description": f"Switch blocks ({config.BLOCK_SWITCH}): passing off and picking "
                       "up rushers who cross on stunts and twists.",
        "prefix": "sw",
        "filter": _stunt_twist,
        "requires_tracking": False,
        "attributes": [
            Attribute("sw_loss_rate", "Switch-block loss rate", 0.40, LOWER, "pct"),
            Attribute("sw_pressure_rate", "Switch-block pressure rate", 0.25, LOWER, "pct"),
            Attribute("loss_rate", "Overall loss rate", 0.15, LOWER, "pct"),
            Attribute("penalty_rate", "Penalty rate", 0.10, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.10, TARGET, "lb", target=305),
        ],
    },
    "blitz": {
        "key": "blitz",
        "name": "Blitz pickup",
        "description": f"Protection when the defense sends {config.BLITZ_MIN_RUSHERS} or "
                       "more pass rushers.",
        "prefix": "blitz",
        "filter": _blitz,
        "requires_tracking": False,
        "attributes": [
            Attribute("blitz_loss_rate",
                      f"Loss rate vs {config.BLITZ_MIN_RUSHERS}+ rushers", 0.35, LOWER, "pct"),
            Attribute("blitz_pressure_rate",
                      f"Pressure rate vs {config.BLITZ_MIN_RUSHERS}+", 0.25, LOWER, "pct"),
            Attribute("blitz_sack_rate",
                      f"Sack rate vs {config.BLITZ_MIN_RUSHERS}+", 0.15, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.15, TARGET, "lb", target=315),
            Attribute("loss_rate", "Overall loss rate", 0.10, LOWER, "pct"),
        ],
    },
    "long_dev": {
        "key": "long_dev",
        "name": "Long-developing protection",
        "description": "Holding the pocket when the quarterback keeps the ball "
                       f"{config.LONG_DEV_MIN_SECONDS:g}+ seconds (needs tracking data).",
        "prefix": "long",
        "filter": _long_dev,
        "requires_tracking": True,
        "attributes": [
            Attribute("long_loss_rate", "Long-play loss rate", 0.30, LOWER, "pct"),
            Attribute("long_pressure_rate", "Long-play pressure rate", 0.25, LOWER, "pct"),
            Attribute("depth_lost_3s", "Depth lost at 3 s", 0.20, LOWER, "yd"),
            Attribute("long_sack_rate", "Long-play sack rate", 0.10, LOWER, "pct"),
            Attribute("weight_lb", "Weight", 0.10, TARGET, "lb", target=312),
            Attribute("penalty_rate", "Penalty rate", 0.05, LOWER, "pct"),
        ],
    },
}


# ------------------------------------------------------------------------- helpers
def enabled_tactics(tracking_used):
    """The tactics that can be ranked: all of them with tracking, otherwise only
    those that do not require it. Keeps TACTICS order."""
    return {key: t for key, t in TACTICS.items()
            if tracking_used or not t["requires_tracking"]}


def active_attributes(tactic, tracking_used):
    """The tactic's attributes in importance order. Without tracking, the tracking
    attributes are dropped and the remaining weights are rescaled proportionally
    (each divided by their sum) so they still add up to 1."""
    attrs = [a for a in tactic["attributes"]
             if tracking_used or a.key not in TRACKING_ATTRIBUTES]
    total = sum(a.weight for a in attrs)
    return [a._replace(weight=a.weight / total) for a in attrs]


def tactic_mask(tactic, snaps):
    """Boolean mask of the snaps that count toward `tactic`; blank fields never match."""
    return tactic["filter"](snaps).astype("boolean").fillna(False).astype(bool)


def _validate(tactics):
    """Fail at import if a tactic definition is inconsistent."""
    better_of, tracking_owner, prefixes = {}, {}, set()
    for key, t in tactics.items():
        if t["key"] != key or t["prefix"] in prefixes:
            raise ValueError(f"tactic {key!r}: key must match and prefix must be unique")
        prefixes.add(t["prefix"])
        total = sum(a.weight for a in t["attributes"])
        if abs(total - 1) > 1e-9:
            raise ValueError(f"tactic {key!r}: weights sum to {total}, not 1")
        for a in t["attributes"]:
            if a.better not in (LOWER, HIGHER, TARGET) or a.format not in FORMATS:
                raise ValueError(f"{key}.{a.key}: unknown better {a.better!r} "
                                 f"or format {a.format!r}")
            if (a.better == TARGET) != (a.target is not None):
                raise ValueError(f"{key}.{a.key}: a target value goes with better='target'")
            # One direction per attribute, so benchmarks.json can hold one ideal/floor.
            if better_of.setdefault(a.key, a.better) != a.better:
                raise ValueError(f"{a.key}: 'better' differs between tactics")
            # A tracking attribute is averaged over one tactic's snaps only.
            if a.key in TRACKING_ATTRIBUTES and tracking_owner.setdefault(a.key, key) != key:
                raise ValueError(f"{a.key}: tracking attribute used by more than one tactic")


_validate(TACTICS)
