"""
Tracking-based values for each center base snap (used only when tracking files exist).

Reads nothing itself: it consumes the whitelisted chunks that data_loader yields,
keeps only the qualifying centers' own rows on their base snaps (those rows carry
the play's event tags), and returns one row per snap with:

  time_to_event  seconds from the snap to the first pass-forward, sack or QB-run tag
  lateral_speed  sum of |change in y| over the 20 frames after the snap, divided by
                 2.0 s: average sideways speed in yd/s
  depth_lost_3s  yards moved back toward his own end zone between the snap and 30
                 frames (3.0 s) later; negative if he moved forward

Tracking runs at config.FRAMES_PER_SECOND (10). A value is left blank (NaN) when its
frames are missing: no snap tag, no end tag after the snap, or a window cut short.
"""
import numpy as np
import pandas as pd

from backend import config

KEYS = ["gameId", "playId", "nflId"]


def keep_center_rows(chunks, base_keys):
    """Stream the chunks, keeping only rows whose (gameId, playId, nflId) is a base
    snap in `base_keys`. Returns (rows, rows_read)."""
    base_keys = base_keys[KEYS].drop_duplicates()
    center_ids = set(base_keys["nflId"])
    kept, rows_read = [], 0
    for chunk in chunks:
        rows_read += len(chunk)
        # Cheap first cut on nflId (ball rows have a blank nflId), then exact keys.
        chunk = chunk[chunk["nflId"].isin(center_ids)].astype({"nflId": "int64"})
        kept.append(chunk.merge(base_keys, on=KEYS))
    if not kept:
        return pd.DataFrame(columns=config.WHITELIST["tracking"]), rows_read
    rows = pd.concat(kept, ignore_index=True).drop_duplicates(KEYS + ["frameId"])
    return rows, rows_read


def _first_listed(frames, names):
    """Per snap, the frame of the first tag in `names` that is present (priority order)."""
    cols = [n for n in names if n in frames.columns]
    if not cols:
        return pd.Series(np.nan, index=frames.index)
    return frames[cols].bfill(axis=1).iloc[:, 0]


def _earliest(frames, names):
    """Per snap, the earliest frame carrying any tag in `names`."""
    cols = [n for n in names if n in frames.columns]
    return frames[cols].min(axis=1) if cols else pd.Series(np.nan, index=frames.index)


def event_frames(rows):
    """Per snap: snap_frame (manual snap tag, else the auto one) and end_frame (the
    first pass-forward, sack or QB-run tag strictly after the snap)."""
    tagged = rows.dropna(subset=["event"])
    first = tagged.groupby(KEYS + ["event"])["frameId"].min().unstack("event")
    snap = _first_listed(first, config.SNAP_EVENTS).dropna().rename("snap_frame")

    after = tagged.merge(snap.reset_index(), on=KEYS)
    after = after[after["frameId"] > after["snap_frame"]]
    first_after = (after.groupby(KEYS + ["event"])["frameId"].min()
                   .unstack("event").reindex(snap.index))
    end = pd.concat([_first_listed(first_after, config.PASS_FORWARD_EVENTS),
                     _earliest(first_after, config.SACK_EVENTS),
                     _earliest(first_after, config.RUN_EVENTS)], axis=1).min(axis=1)
    return pd.DataFrame({"snap_frame": snap, "end_frame": end})


def window_features(rows, snap_frame):
    """lateral_speed and depth_lost_3s, measured from each snap's own snap frame."""
    fps = config.FRAMES_PER_SECOND
    lat_frames, depth_frames = config.LATERAL_WINDOW_FRAMES, config.DEPTH_WINDOW_FRAMES
    r = rows.merge(snap_frame.reset_index(), on=KEYS)
    r["k"] = r["frameId"] - r["snap_frame"]            # frames since the snap

    # lateral_speed: frames 0..20 must all exist (21 positions, 20 steps).
    w = r[r["k"].between(0, lat_frames)].sort_values(KEYS + ["k"])
    w = w.assign(dy=w.groupby(KEYS)["y"].diff().abs())
    steps = w.groupby(KEYS).agg(frames=("k", "size"), path=("dy", "sum"))
    lateral_speed = (steps["path"] / (lat_frames / fps)).where(steps["frames"] == lat_frames + 1)

    # depth_lost_3s: x at the snap minus x 30 frames later, times +1 if the offense
    # attacks increasing x (playDirection 'right') or -1 if it attacks decreasing x,
    # so moving back toward his own end zone is positive either way.
    at_snap = r[r["k"] == 0].set_index(KEYS)
    x_later = r[r["k"] == depth_frames].set_index(KEYS)["x"]
    sign = at_snap["playDirection"].map(config.PLAY_DIRECTION_SIGN)
    depth_lost = (at_snap["x"] - x_later) * sign

    return pd.DataFrame({"lateral_speed": lateral_speed, "depth_lost_3s": depth_lost})


def snap_features(chunks, base_keys):
    """One row per base snap with tracking: KEYS + time_to_event, lateral_speed,
    depth_lost_3s. Also returns a dict of row and snap counts for meta.json."""
    columns = ["time_to_event", "lateral_speed", "depth_lost_3s"]
    rows, rows_read = keep_center_rows(chunks, base_keys)
    if rows.empty:
        return pd.DataFrame(columns=KEYS + columns), {"trackingRowsRead": rows_read,
                                                      "trackingRowsKept": 0}
    frames = event_frames(rows)
    out = frames.join(window_features(rows, frames["snap_frame"]), how="left")
    out["time_to_event"] = (out["end_frame"] - out["snap_frame"]) / config.FRAMES_PER_SECOND
    coverage = {
        "trackingRowsRead": rows_read,
        "trackingRowsKept": len(rows),
        "snapsWithTrackingRows": len(rows[KEYS].drop_duplicates()),
        "snapsWithSnapTag": int(frames["snap_frame"].notna().sum()),
        "snapsWithTimeToEvent": int(out["time_to_event"].notna().sum()),
        "snapsWithLateralSpeed": int(out["lateral_speed"].notna().sum()),
        "snapsWithDepthLost3s": int(out["depth_lost_3s"].notna().sum()),
    }
    return out[columns].reset_index(), coverage
