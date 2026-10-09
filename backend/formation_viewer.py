"""
Animated formation / play viewer with a slider.

Run it
------
    python app.py                                      # 1. the backend API (another terminal)
    python -m backend.formation_viewer                 # 2. bundled Big Data Bowl data
    python -m backend.formation_viewer --demo          # synthetic plays
    python -m backend.formation_viewer --data path/to/bdb
    python -m backend.formation_viewer --api http://127.0.0.1:5001   # API address

For --data, the folder needs plays.csv and the tracking files, either as
    path/to/bdb/tracking_<gameId>.csv   or   path/to/bdb/tracking/tracking_<gameId>.csv
players.csv and pffScoutingData.csv are used for names/positions if present.

Headless test (no window, saves one frame):
    python -m backend.formation_viewer --snapshot out.png --formation I_FORM --frame 30

Needs: pandas, numpy, matplotlib (Tkinter ships with most Python installs).

In the window: pick a formation and a play, press Play or drag the slider,
choose a tactic, then click a player to highlight them and see their trail on
the right. Tactic rankings come from the backend's Flask API (backend/api.py),
which scores and ranks the centers afresh on every request: with no player
selected the panel lists the tactic's top 15; select a center to see his rank,
suitability and attribute breakdown. If the API is not running, the panel says
how to start it.
"""
import argparse
import json
import os
from pathlib import Path
from urllib import error, parse, request

import numpy as np
import pandas as pd

from backend import config
from backend.tactics import TACTICS

FPS = 10
SNAP_FRAME = 11          # demo plays: frame at which the ball is snapped
LOS_X = 60.0             # demo plays: line of scrimmage (offense moves to +x)
Y_MID = 26.65
COLORS = {"offense": "#1f77b4", "defense": "#d62728", "ball": "#8b4513"}

# ----------------------------------------------------------------------------
# Tactic rankings from the backend (Flask API started with `python app.py`)
# ----------------------------------------------------------------------------
# Tactic names and the priority order of their attributes come from
# backend/tactics.py; every number (rank, suitability, values, scores) comes from
# the API, which scores and ranks the centers afresh on each request.
TACTIC_KEYS = {t["name"]: key for key, t in TACTICS.items()}   # dropdown label -> key
DEFAULT_API_URL = f"http://{config.API_HOST}:{config.API_PORT}"
TOP_N = config.DEFAULT_LIMIT


class BackendUnavailable(RuntimeError):
    """The Flask API could not be reached, or answered with an error."""


class RankingsClient:
    """Reads tactic rankings from the backend's Flask API (backend/api.py)."""

    def __init__(self, base_url=DEFAULT_API_URL, timeout=3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Talk to the local server directly, never through a system proxy.
        self._opener = request.build_opener(request.ProxyHandler({}))

    def rankings(self, tactic_key, limit=config.MAX_LIMIT):
        """GET /api/rankings for one tactic: every ranked center (up to `limit`), best first."""
        query = parse.urlencode({"tactic": tactic_key, "limit": limit})
        return self._get(f"/api/rankings?{query}")

    def _get(self, path):
        url = self.base_url + path
        try:
            with self._opener.open(url, timeout=self.timeout) as response:
                return json.load(response)
        except error.HTTPError as err:              # the API answered {"error": ...}
            try:
                message = json.load(err).get("error")
            except (ValueError, AttributeError):
                message = None
            raise BackendUnavailable(message or f"HTTP {err.code} from {url}") from None
        except (error.URLError, OSError):           # nothing listening, or a timeout
            raise BackendUnavailable(
                f"Backend API not reachable at {self.base_url}. Start it with "
                "`python app.py`, then pick the tactic again.") from None


def tactic_priorities(tactic_key):
    """The tactic's attribute labels in importance order (backend/tactics.py)."""
    return [attr.label for attr in TACTICS[tactic_key]["attributes"]]


def find_player(ranking, nfl_id):
    """The /api/rankings entry for `nfl_id`, or None if he is not ranked."""
    return next((p for p in ranking["players"] if p["nflId"] == nfl_id), None)


def format_top_ranking(ranking, n=TOP_N):
    """The first n centers of a /api/rankings response, one line each."""
    players = ranking["players"][:n]
    lines = [f"{ranking['tacticName']}: top {len(players)} centers",
             "(scored and ranked by the backend just now)", ""]
    lines += [f"{p['rank']:>2}. {p['name']} ({p['team']})  ·  {p['suitability']:.1f}%  ·  "
              f"{p['confidence']}" for p in players]
    return "\n".join(lines)


def format_player_ranking(ranking, nfl_id):
    """One center's rank, suitability and attribute breakdown for the tactic."""
    p = find_player(ranking, nfl_id)
    if p is None:
        return (f"{ranking['tacticName']}\nNot ranked: only centers with at least "
                f"{config.MIN_BASE_SNAPS} pass-block snaps at C are ranked.")
    labels = {c["key"]: c["label"] for c in ranking["columns"]}
    lines = [ranking["tacticName"],
             f"Rank {p['rank']} of {len(ranking['players'])}  ·  "
             f"suitability {p['suitability']:.1f}%",
             f"Confidence {p['confidence']} ({p['tacticSnaps']} tactic snaps, "
             f"{p['baseSnaps']} base snaps)", ""]
    for c in ranking["columns"]:
        a = p["attributes"][c["key"]]
        lines.append(f"{c['label']}: {a['display']}  "
                     f"(score {a['score']}/100, weight {c['weight']:.0%})")
    lines += ["", f"Top strength: {labels[p['topStrength']]}",
              f"Biggest concern: {labels[p['biggestConcern']]}"]
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Demo formations: (dx, dy) offsets from the LOS / field centre, offense moving +x
# ----------------------------------------------------------------------------
FORMATIONS = {
    "SHOTGUN": dict(qb=(-5.0, 0.0), drop=0.5,
                    backs=[(-5.0, 2.5, "route")],
                    tes=[(-0.5, 4.5)],
                    wrs=[(-0.5, -19.0), (-0.5, -11.0), (-0.5, 18.0)]),
    "SINGLEBACK": dict(qb=(-2.0, 0.0), drop=4.0,
                       backs=[(-6.0, 0.0, "route")],
                       tes=[(-0.5, 4.5), (-0.5, -4.5)],
                       wrs=[(-0.5, -19.0), (-0.5, 18.0)]),
    "I_FORM": dict(qb=(-2.0, 0.0), drop=4.5,
                   backs=[(-4.5, 0.0, "block"), (-7.0, 0.0, "route")],
                   tes=[(-0.5, 4.5)],
                   wrs=[(-0.5, -19.0), (-0.5, 18.0)]),
    "EMPTY": dict(qb=(-5.0, 0.0), drop=0.5, backs=[],
                  tes=[(-0.5, 4.5)],
                  wrs=[(-0.5, -20.0), (-0.5, -12.0), (-0.5, 12.0), (-0.5, 19.0)]),
    "PISTOL": dict(qb=(-3.5, 0.0), drop=2.5,
                   backs=[(-6.5, 0.0, "route")],
                   tes=[(-0.5, 4.5)],
                   wrs=[(-0.5, -19.0), (-0.5, -11.0), (-0.5, 18.0)]),
}
ROUTE_CYCLE = ["go", "out", "in", "curl", "out", "go"]


def _route_path(tp, x0, y0, kind, sgn, stem_t):
    a = np.clip(tp - stem_t, 0, None)
    x = x0 + 7.5 * np.minimum(tp, stem_t)
    y = np.full(len(tp), y0, dtype=float)
    if kind == "go":
        x = x + 7.5 * a
    elif kind == "out":
        a = np.minimum(a, 2.0)
        x, y = x + 2.0 * a, y + sgn * 6.0 * a
    elif kind == "in":
        a = np.minimum(a, 2.5)
        x, y = x + 2.0 * a, y - sgn * 6.5 * a
    elif kind == "curl":
        a = np.minimum(a, 1.0)
        x, y = x - 3.0 * a, y + sgn * 1.0 * a
    return x, np.clip(y, 2.0, 51.3)


def _chase(tp, x0, y0, tx, ty, speed, start_t=0.0, slow_until=0.0, slow_factor=1.0, stop=1.0):
    n = len(tp)
    x, y = np.empty(n), np.empty(n)
    cx, cy = x0, y0
    for k in range(n):
        if tp[k] >= start_t:
            dx, dy = tx[k] - cx, ty[k] - cy
            d = float(np.hypot(dx, dy))
            step = speed * (slow_factor if tp[k] < slow_until else 1.0) / FPS
            if d > stop:
                step = min(step, d - stop)
                cx += dx / d * step
                cy += dy / d * step
        x[k], y[k] = cx, cy
    return x, y


def build_demo_play(formation, variant=0):
    """Synthetic dropback play in the same long format as the real tracking data."""
    spec = FORMATIONS[formation]
    rng = np.random.default_rng(1000 * (list(FORMATIONS).index(formation) + 1) + variant)
    T = 60
    frames = np.arange(1, T + 1)
    tp = np.clip((frames - SNAP_FRAME) / FPS, 0, None)  # seconds since snap
    players = []

    def add(name, pos, side, jersey, x, y):
        players.append(dict(displayName=name, position=pos, side=side,
                            jerseyNumber=jersey, x=np.asarray(x, float), y=np.asarray(y, float)))

    # quarterback
    qx = LOS_X + spec["qb"][0] - np.minimum(tp * 3.5, spec["drop"])
    qy = np.full(T, Y_MID)
    add("Demo QB", "QB", "offense", 12, qx, qy)

    # offensive line
    for pos, dy, jn in zip(["LT", "LG", "C", "RG", "RT"], [-3, -1.5, 0, 1.5, 3], [72, 66, 63, 64, 75]):
        x = LOS_X - 0.5 - np.minimum(tp, 1.0) * 1.3
        y = Y_MID + dy + 0.15 * np.sin(tp * 6 + dy)
        add(f"Demo {pos}", pos, "offense", jn, x, y)

    # eligible receivers (WR + TE) with routes
    receivers = [("WR", jn, dx, dy) for jn, (dx, dy) in zip([11, 13, 18, 83], spec["wrs"])]
    receivers += [("TE", jn, dx, dy) for jn, (dx, dy) in zip([85, 87], spec["tes"])]
    rec_paths = []
    for i, (pos, jn, dx, dy) in enumerate(receivers):
        sgn = 1.0 if dy >= 0 else -1.0
        kind = ROUTE_CYCLE[(i + variant) % len(ROUTE_CYCLE)]
        stem = 1.3 + rng.uniform(0, 0.5)
        x, y = _route_path(tp, LOS_X + dx, Y_MID + dy, kind, sgn, stem)
        rec_paths.append((x, y, Y_MID + dy))
        add(f"Demo {pos} {jn}", pos, "offense", jn, x, y)

    # running backs
    for i, (dx, dy, role) in enumerate(spec["backs"]):
        x0, y0 = LOS_X + dx, Y_MID + dy
        if role == "route":
            sgn = 1.0 if (dy > 0 or (dy == 0 and (variant + i) % 2 == 0)) else -1.0
            x = x0 + 2.5 * np.minimum(tp, 1.5)
            y = np.clip(y0 + sgn * 5.5 * np.minimum(tp, 1.8), 2, 51.3)
            add("Demo RB", "RB", "offense", 28, x, y)
        else:
            x = x0 + 2.0 * np.minimum(tp, 0.8)
            add("Demo FB", "FB", "offense", 40, x, np.full(T, y0))

    # defense: 4-3 with two high safeties
    blitz = (variant % 2 == 1)
    for pos, dy, jn in zip(["DE", "DT", "DT", "DE"], [-4.5, -1.5, 1.5, 4.5], [91, 94, 97, 99]):
        wins = rng.uniform(1.6, 5.0)
        x, y = _chase(tp, LOS_X + 0.7, Y_MID + dy, qx, qy + 0.6 * dy, 5.8,
                      start_t=rng.uniform(0.1, 0.3), slow_until=wins, slow_factor=0.15, stop=1.2)
        add(f"Demo {pos} {jn}", pos, "defense", jn, x, y)
    for i, (pos, dy, jn) in enumerate(zip(["OLB", "MLB", "OLB"], [-6, 0, 6], [52, 54, 56])):
        if blitz and i == 1:
            x, y = _chase(tp, LOS_X + 4.5, Y_MID + dy, qx, qy, 6.0, start_t=0.2,
                          slow_until=rng.uniform(1.5, 3.0), slow_factor=0.4)
        else:
            x = LOS_X + 4.5 + np.minimum(tp * 3.5, 6.0)
            y = np.full(T, Y_MID + dy) + 0.3 * np.sin(tp * 2 + i)
        add(f"Demo {pos} {jn}", pos, "defense", jn, x, y)

    # cornerbacks shadow the two widest receivers
    wide = sorted(range(len(receivers)), key=lambda i: receivers[i][3])
    for jn, ri in zip([21, 24], [wide[0], wide[-1]]):
        rx, ry, ry0 = rec_paths[ri]
        x, y = _chase(tp, LOS_X + 4.5, ry0, rx + 4.0, ry, 7.3, start_t=0.2, stop=0.3)
        add(f"Demo CB {jn}", "CB", "defense", jn, x, y)

    # safeties
    for jn, sgn in zip([31, 32], [-1.0, 1.0]):
        x = LOS_X + 10 + np.minimum(tp * 3.5, 6.0)
        y = Y_MID + sgn * 8 + sgn * np.minimum(tp * 1.5, 3.0)
        add(f"Demo S {jn}", "S", "defense", jn, x, y)

    # ball: snap -> QB, then thrown to a receiver
    t_rel, t_arr = 2.8, 3.7
    tgt = int(rng.integers(len(receivers)))
    tx, ty = rec_paths[tgt][0], rec_paths[tgt][1]
    k_rel = int(np.argmax(tp >= t_rel))
    k_arr = int(np.argmax(tp >= t_arr))
    bx, by = np.empty(T), np.empty(T)
    for k in range(T):
        if tp[k] <= 0:
            bx[k], by[k] = LOS_X, Y_MID
        elif tp[k] < 0.4:
            f = tp[k] / 0.4
            bx[k] = LOS_X + f * (qx[k] - LOS_X)
            by[k] = Y_MID + f * (qy[k] - Y_MID)
        elif k < k_rel:
            bx[k], by[k] = qx[k], qy[k]
        elif k < k_arr:
            f = (k - k_rel) / (k_arr - k_rel)
            bx[k] = qx[k_rel] + f * (tx[k_arr] - qx[k_rel])
            by[k] = qy[k_rel] + f * (ty[k_arr] - qy[k_rel])
        else:
            bx[k], by[k] = tx[k], ty[k]
    ball = dict(displayName="Ball", position="BALL", side="ball", jerseyNumber=np.nan, x=bx, y=by)

    events = {SNAP_FRAME: "ball_snap",
              SNAP_FRAME + int(round(t_rel * FPS)): "pass_forward",
              SNAP_FRAME + int(round(t_arr * FPS)): "pass_arrived"}
    ev_col = [events.get(int(f)) for f in frames]

    parts = []
    for pid, p in enumerate(players + [ball]):
        is_ball = p["side"] == "ball"
        s = np.r_[0.0, np.hypot(np.diff(p["x"]), np.diff(p["y"])) * FPS]
        parts.append(pd.DataFrame(dict(
            gameId=0, playId=variant, key=-1 if is_ball else pid,
            nflId=np.nan if is_ball else pid, frameId=frames,
            jerseyNumber=p["jerseyNumber"], side=p["side"], x=p["x"], y=p["y"], s=s,
            event=ev_col, displayName=p["displayName"], position=p["position"])))
    return pd.concat(parts, ignore_index=True)


# ----------------------------------------------------------------------------
# Data sources
# ----------------------------------------------------------------------------
class DemoSource:
    label = "DEMO data (synthetic)"

    def formations(self):
        return list(FORMATIONS)

    def plays(self, formation):
        return [(f"Variant {i + 1}" + ("  (MLB blitz)" if i % 2 else ""), (formation, i)) for i in range(4)]

    def load(self, key):
        return build_demo_play(*key)


class RealSource:
    def __init__(self, folder):
        self.folder = folder
        self.label = f"Real data: {folder}"
        self.plays_df = pd.read_csv(os.path.join(folder, "plays.csv"))
        p = os.path.join(folder, "players.csv")
        self.players = pd.read_csv(p) if os.path.exists(p) else None
        p = os.path.join(folder, "pffScoutingData.csv")
        self.pff = (pd.read_csv(p, usecols=["gameId", "playId", "nflId", "pff_positionLinedUp"])
                    if os.path.exists(p) else None)
        self._gid, self._tracking = None, None

    def formations(self):
        return sorted(self.plays_df.offenseFormation.dropna().unique())

    def plays(self, formation):
        d = self.plays_df[self.plays_df.offenseFormation == formation].head(500)
        out = []
        for r in d.itertuples():
            out.append((f"G{r.gameId} P{r.playId} | Q{r.quarter} {r.down}&{r.yardsToGo} | {r.passResult}",
                        (int(r.gameId), int(r.playId))))
        return out

    def _tracking_for(self, gid):
        if gid != self._gid:
            for pat in (f"tracking/tracking_{gid}.csv", f"tracking_{gid}.csv"):
                path = os.path.join(self.folder, pat)
                if os.path.exists(path):
                    break
            else:
                raise FileNotFoundError(f"tracking_{gid}.csv not found under {self.folder}")
            self._tracking, self._gid = pd.read_csv(path), gid
        return self._tracking

    def load(self, key):
        gid, pid = key
        df = self._tracking_for(gid)
        df = df[df.playId == pid].copy()
        flip = df.playDirection.eq("left")
        df.loc[flip, "x"] = 120 - df.loc[flip, "x"]
        df.loc[flip, "y"] = 53.3 - df.loc[flip, "y"]
        offense = self.plays_df.loc[(self.plays_df.gameId == gid) & (self.plays_df.playId == pid),
                                    "possessionTeam"].iloc[0]
        df["side"] = np.where(df.team == "football", "ball",
                              np.where(df.team == offense, "offense", "defense"))
        df["key"] = df.nflId.fillna(-1).astype(int)
        df["displayName"], df["position"] = "Ball", "BALL"
        if self.players is not None:
            m = df[["nflId"]].merge(self.players, on="nflId", how="left")
            if "displayName" in m:
                has = m.displayName.notna().to_numpy()
                df.loc[has, "displayName"] = m.displayName.to_numpy()[has]
            if "officialPosition" in m:
                has = m.officialPosition.notna().to_numpy()
                df.loc[has, "position"] = m.officialPosition.to_numpy()[has]
        if self.pff is not None:
            sub = self.pff[(self.pff.gameId == gid) & (self.pff.playId == pid)]
            mp = dict(zip(sub.nflId, sub.pff_positionLinedUp))
            lined = df.nflId.map(mp)
            df.loc[lined.notna(), "position"] = lined[lined.notna()]
        return df


def build_source(data_dir=None, demo=False):
    """Load the bundled data by default, or synthetic plays when requested."""
    if demo:
        return DemoSource()
    default_data_dir = Path(__file__).resolve().parents[1] / "data" / "raw"
    return RealSource(data_dir or default_data_dir)


# ----------------------------------------------------------------------------
# Rendering (no Tk needed, so it can also be used for snapshots)
# ----------------------------------------------------------------------------
def prepare(df):
    df = df.drop_duplicates(["frameId", "key"])
    frames = np.sort(df.frameId.unique())
    meta = df.drop_duplicates("key").set_index("key")[["side", "jerseyNumber", "displayName", "position"]]
    keys = list(meta.index)

    def piv(col):
        return (df.pivot(index="frameId", columns="key", values=col)
                  .reindex(index=frames, columns=keys).to_numpy(float))

    X, Y, S = piv("x"), piv("y"), piv("s")
    events = {}
    if "event" in df:
        ev = df.dropna(subset=["event"]).drop_duplicates("frameId")
        events = {int(f): e for f, e in zip(ev.frameId, ev.event)}
    snap_idx = next((i for i, f in enumerate(frames) if events.get(int(f)) == "ball_snap"), 0)
    los = X[snap_idx, keys.index(-1)] if -1 in keys else np.nanmean(X[snap_idx])
    return dict(frames=frames, keys=keys, meta=meta, X=X, Y=Y, S=S,
                events=events, snap_idx=snap_idx, los=float(los))


class FieldRenderer:
    def __init__(self, fig):
        self.fig = fig
        self.ax = fig.add_subplot(111)
        self.p = None

    def set_play(self, df):
        self.df = df
        p = self.p = prepare(df)
        ax = self.ax
        ax.clear()
        ax.set_facecolor("#2e7d32")
        lo, hi = max(0, p["los"] - 20), min(120, p["los"] + 60)
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, 53.3)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for x in range(10, 111, 5):
            ax.axvline(x, color="white", alpha=0.35 if x % 10 else 0.6, lw=1)
        for x in range(20, 101, 10):
            n = int(50 - abs(x - 60))
            for y in (5, 48.3):
                ax.text(x, y, str(n), color="white", alpha=0.45, ha="center", va="center", fontsize=11)
        ax.axvline(p["los"], color="#ffd54f", lw=2, alpha=0.9, zorder=1)

        side = p["meta"]["side"].to_numpy()
        self.colors = [COLORS[s] for s in side]
        sizes = np.where(side == "ball", 60, 220)
        self.scat = ax.scatter(p["X"][0], p["Y"][0], s=sizes, c=self.colors,
                               edgecolors="none", linewidths=2.5, zorder=3)
        self.texts = []
        for k in p["keys"]:
            j = p["meta"].loc[k, "jerseyNumber"]
            label = "" if pd.isna(j) else str(int(j))
            self.texts.append(ax.text(0, 0, label, color="white", fontsize=7,
                                      ha="center", va="center", zorder=4, fontweight="bold"))
        self.trail, = ax.plot([], [], color="#ffeb3b", lw=1.8, zorder=2)
        self.title = ax.set_title("", fontsize=10)
        self.fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.93)
        self.draw_frame(0)

    def draw_frame(self, i, selected=None):
        p = self.p
        xs, ys = p["X"][i].copy(), p["Y"][i].copy()
        bad = np.isnan(xs) | np.isnan(ys)
        xs[bad], ys[bad] = -100, -100
        self.scat.set_offsets(np.c_[xs, ys])
        edges = ["yellow" if (selected is not None and k == selected) else "none" for k in p["keys"]]
        self.scat.set_edgecolors(edges)
        for t, x, y, b in zip(self.texts, xs, ys, bad):
            t.set_position((x, y))
            t.set_visible(not b)
        if selected is not None and selected in p["keys"]:
            c = p["keys"].index(selected)
            self.trail.set_data(p["X"][:i + 1, c], p["Y"][:i + 1, c])
        else:
            self.trail.set_data([], [])
        f = int(p["frames"][i])
        ev = p["events"].get(f, "")
        rel = (i - p["snap_idx"]) / FPS
        self.title.set_text(f"frame {f}   t = {rel:+.1f}s from snap   {ev}")

    def nearest(self, i, x, y, radius=3.0):
        p = self.p
        d = np.hypot(p["X"][i] - x, p["Y"][i] - y)
        if np.all(np.isnan(d)):
            return None
        j = int(np.nanargmin(d))
        return p["keys"][j] if d[j] <= radius else None

    def describe(self, key, i):
        p = self.p
        c = p["keys"].index(key)
        m = p["meta"].loc[key]
        s = p["S"][:, c]
        dist = np.nansum(s) / FPS
        j = "" if pd.isna(m.jerseyNumber) else f"#{int(m.jerseyNumber)}"
        return (f"{m.displayName} {j}\n"
                f"position : {m.position}\n"
                f"side     : {m.side}\n\n"
                f"Play tracking (not tactic metrics)\n"
                f"speed now: {s[i]:.1f} yd/s\n"
                f"top speed: {np.nanmax(s):.1f} yd/s\n"
                f"distance : {dist:.1f} yd (whole play)\n"
                f"x, y     : {p['X'][i, c]:.1f}, {p['Y'][i, c]:.1f}")

    def center_key(self):
        """Tracking key of the player lined up at C in this play, if any."""
        positions = self.p["meta"]["position"]
        centers = positions.index[positions == config.CENTER_POSITION]
        return centers[0] if len(centers) else None


def player_options(meta):
    """Return readable, unique player labels and their tracking keys."""
    options = []
    keys_by_label = {}
    for key, player in meta.iterrows():
        if player.side == "ball":
            continue
        jersey = "" if pd.isna(player.jerseyNumber) else f" #{int(player.jerseyNumber)}"
        position = "" if pd.isna(player.position) else f" · {player.position}"
        label = f"{player.displayName}{jersey}{position}"
        if label in keys_by_label:
            label = f"{label} · ID {key}"
        options.append(label)
        keys_by_label[label] = key
    return options, keys_by_label


def frame_status(prepared, index):
    """Build a concise timeline status from the currently displayed frame."""
    index = min(max(int(index), 0), len(prepared["frames"]) - 1)
    frame = int(prepared["frames"][index])
    elapsed = (index - prepared["snap_idx"]) / FPS
    event = prepared["events"].get(frame, "")
    message = f"Frame {frame}  ·  {elapsed:+.1f}s from snap"
    return f"{message}  ·  {event}" if event else message


# ----------------------------------------------------------------------------
# Tk app
# ----------------------------------------------------------------------------
def run_gui(source, client=None):
    client = client or RankingsClient()
    import matplotlib
    matplotlib.use("TkAgg")
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    root = tk.Tk()
    root.title("NFL Formation & Play Viewer")
    root.geometry("1240x800")
    root.minsize(900, 600)
    root.configure(bg="#eef2f5")
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("App.TFrame", background="#eef2f5")
    style.configure("Card.TFrame", background="#ffffff")
    style.configure("Title.TLabel", background="#eef2f5", foreground="#172b3a",
                    font=("Segoe UI", 17, "bold"))
    style.configure("Subtitle.TLabel", background="#eef2f5", foreground="#526575",
                    font=("Segoe UI", 9))
    style.configure("Section.TLabel", background="#ffffff", foreground="#172b3a",
                    font=("Segoe UI", 11, "bold"))
    style.configure("Hint.TLabel", background="#ffffff", foreground="#526575",
                    font=("Segoe UI", 9))
    style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
    style.configure("TCombobox", padding=4)
    # ranking: the latest /api/rankings response for the chosen tactic (or None);
    # ranking_error: why it could not be fetched (or None).
    state = dict(playing=False, speed=1.0, selected=None, plays=[],
                 player_labels={}, after_id=None, ranking=None, ranking_error=None)

    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)
    header = ttk.Frame(root, style="App.TFrame", padding=(16, 12, 16, 8))
    header.grid(row=0, column=0, sticky="ew")
    ttk.Label(header, text="NFL Formation & Play Viewer", style="Title.TLabel").pack(anchor="w")
    ttk.Label(header, text="Review player movement by formation and inspect available tactic attributes.",
              style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

    controls = ttk.Frame(root, style="Card.TFrame", padding=(12, 10))
    controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
    controls.columnconfigure(1, weight=1)
    controls.columnconfigure(3, weight=2)
    ttk.Label(controls, text="FORMATION", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
    form_cb = ttk.Combobox(controls, values=source.formations(), state="readonly", width=18)
    form_cb.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(3, 0))
    ttk.Label(controls, text="PLAY", style="Hint.TLabel").grid(row=0, column=1, sticky="w")
    play_cb = ttk.Combobox(controls, state="readonly")
    play_cb.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(3, 0))
    ttk.Label(controls, text="PLAYER", style="Hint.TLabel").grid(row=0, column=2, sticky="w")
    player_cb = ttk.Combobox(controls, state="readonly", width=24)
    player_cb.grid(row=1, column=2, sticky="ew", padx=(0, 12), pady=(3, 0))
    ttk.Label(controls, text="TACTIC ANALYSIS", style="Hint.TLabel").grid(row=0, column=3, sticky="w")
    tactic_cb = ttk.Combobox(controls, values=list(TACTIC_KEYS), state="readonly")
    tactic_cb.grid(row=1, column=3, sticky="ew", pady=(3, 0))
    tactic_cb.set("")

    # A resizable split lets the field retain priority while keeping details visible.
    body = ttk.Panedwindow(root, orient="horizontal")
    body.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
    field_card = ttk.Frame(body, style="Card.TFrame", padding=8)
    detail_card = ttk.Frame(body, style="Card.TFrame", padding=12)
    body.add(field_card, weight=4)
    body.add(detail_card, weight=1)
    field_card.rowconfigure(0, weight=1)
    field_card.columnconfigure(0, weight=1)
    fig = Figure(figsize=(9, 5.2), dpi=100, facecolor="white")
    renderer = FieldRenderer(fig)
    canvas = FigureCanvasTkAgg(fig, master=field_card)
    canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
    detail_card.columnconfigure(0, weight=1)
    detail_card.rowconfigure(2, weight=1)
    ttk.Label(detail_card, text="PLAYER INSPECTOR", style="Section.TLabel").grid(
        row=0, column=0, sticky="w")
    selected_status = ttk.Label(detail_card, text="No player selected",
                                style="Hint.TLabel", wraplength=260)
    selected_status.grid(row=1, column=0, sticky="ew", pady=(4, 8))
    text_frame = ttk.Frame(detail_card)
    text_frame.grid(row=2, column=0, sticky="nsew")
    text_frame.rowconfigure(0, weight=1)
    text_frame.columnconfigure(0, weight=1)
    info = tk.Text(text_frame, wrap="word", relief="flat", borderwidth=0,
                   padx=8, pady=8, font=("Segoe UI", 10), bg="#f6f8fa",
                   fg="#263746", state="disabled")
    info.grid(row=0, column=0, sticky="nsew")
    info_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=info.yview)
    info_scroll.grid(row=0, column=1, sticky="ns")
    info.configure(yscrollcommand=info_scroll.set)
    ttk.Label(detail_card, text="Click a player on the field or choose one above.",
              style="Hint.TLabel", wraplength=260).grid(row=3, column=0, sticky="w", pady=(8, 0))

    playback = ttk.Frame(root, style="Card.TFrame", padding=(12, 8))
    playback.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
    playback.columnconfigure(4, weight=1)
    btn = ttk.Button(playback, text="▶  Play", style="Accent.TButton")
    btn.grid(row=0, column=0, padx=(0, 6))
    ttk.Button(playback, text="◀ Frame", command=lambda: goto(slider.get() - 1)).grid(
        row=0, column=1, padx=3)
    ttk.Button(playback, text="Snap", command=lambda: goto_snap()).grid(
        row=0, column=2, padx=3)
    ttk.Button(playback, text="Frame ▶", command=lambda: goto(slider.get() + 1)).grid(
        row=0, column=3, padx=(3, 10))
    slider = tk.Scale(playback, from_=0, to=1, orient="horizontal", showvalue=False,
                      highlightthickness=0, bd=0, bg="#ffffff", troughcolor="#d9e2e9",
                      activebackground="#2375a5")
    slider.grid(row=0, column=4, sticky="ew")
    speed_cb = ttk.Combobox(playback, values=["0.25x", "0.5x", "1x", "2x"],
                            state="readonly", width=7)
    speed_cb.set("1x")
    speed_cb.grid(row=0, column=5, padx=(10, 0))
    frame_label = ttk.Label(playback, text="Frame —", width=30, anchor="e")
    frame_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=(5, 0))
    source_status = ttk.Label(root, text=f"{source.label}  ·  rankings from {client.base_url}",
                              style="Subtitle.TLabel", anchor="w")
    source_status.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 8))

    def set_info(text):
        info.configure(state="normal")
        info.delete("1.0", "end")
        info.insert("1.0", text)
        info.configure(state="disabled")

    def show_empty_state(message):
        renderer.p = None
        state["selected"] = None
        player_cb.configure(values=[])
        player_cb.set("")
        renderer.ax.clear()
        renderer.ax.set_axis_off()
        renderer.ax.text(0.5, 0.5, message, transform=renderer.ax.transAxes,
                         ha="center", va="center", color="#526575", fontsize=12)
        canvas.draw_idle()
        selected_status.config(text="No player selected")
        frame_label.config(text=message)
        set_info(message)
        btn.config(state="disabled")
        slider.config(state="disabled")

    def fetch_ranking():
        """Ask the API for the chosen tactic's ranking; the backend computes it afresh."""
        key = TACTIC_KEYS.get(tactic_cb.get())
        state["ranking"], state["ranking_error"] = None, None
        if key is None:
            return
        try:
            state["ranking"] = client.rankings(key)
        except BackendUnavailable as exc:
            state["ranking_error"] = str(exc)

    def tactic_text(selected):
        """Tactic panel text: the selected player's breakdown, or the top 15."""
        key = TACTIC_KEYS.get(tactic_cb.get())
        if key is None:
            return ""
        ranking = state["ranking"]
        if ranking is None:
            priorities = "\n".join(f"{n}. {label}"
                                   for n, label in enumerate(tactic_priorities(key), start=1))
            return (f"{tactic_cb.get()}\n{state['ranking_error'] or 'No ranking loaded.'}"
                    f"\n\nPriority attributes\n{priorities}")
        if selected is not None:
            return format_player_ranking(ranking, selected)
        text = format_top_ranking(ranking)
        center = renderer.center_key()
        if center is not None:
            name = renderer.p["meta"].loc[center, "displayName"]
            p = find_player(ranking, center)
            text += (f"\n\nCenter in this play: {name}, "
                     + (f"rank {p['rank']} ({p['suitability']:.1f}%)" if p else "not ranked"))
        return text + "\n\nClick a center on the field to see his breakdown."

    def render(i):
        if renderer.p is None:
            return
        i = min(max(int(i), 0), len(renderer.p["frames"]) - 1)
        renderer.draw_frame(i, state["selected"])
        canvas.draw_idle()
        frame_label.config(text=frame_status(renderer.p, i))
        if state["selected"] is not None:
            selected = renderer.p["meta"].loc[state["selected"]]
            selected_status.config(
                text=f"{selected.displayName}  ·  {selected.position}  ·  {selected.side}"
            )
            details = renderer.describe(state["selected"], i)
            ranking_text = tactic_text(state["selected"])
            set_info(f"{ranking_text}\n\n{details}" if ranking_text else details)
        elif TACTIC_KEYS.get(tactic_cb.get()):
            selected_status.config(text=f"Tactic: {tactic_cb.get()}")
            set_info(tactic_text(None))
        else:
            selected_status.config(text="No player selected")
            set_info("Choose a player to view play-tracking details. Select a tactic to "
                     "see its top 15 centers, then click a center for his breakdown.")

    def update_player_choices():
        labels, state["player_labels"] = player_options(renderer.p["meta"])
        player_cb.configure(values=labels)
        player_cb.set("")

    def select_player(key):
        state["selected"] = key
        if key is None:
            player_cb.set("")
        else:
            label = next((label for label, player_key in state["player_labels"].items()
                          if player_key == key), "")
            player_cb.set(label)
        if TACTIC_KEYS.get(tactic_cb.get()):
            fetch_ranking()                     # fresh ranking for each new selection
        render(slider.get())

    def on_tactic(_=None):
        fetch_ranking()
        render(slider.get())

    def goto(i):
        if renderer.p is None:
            return
        i = min(max(int(i), 0), len(renderer.p["frames"]) - 1)
        slider.set(i)
        render(i)

    def on_slider(v):
        if renderer.p is not None:
            render(int(float(v)))

    slider.config(command=on_slider)

    def set_playing(flag):
        if not flag and state["after_id"] is not None:
            try:
                root.after_cancel(state["after_id"])
            except tk.TclError:
                pass
            state["after_id"] = None
        state["playing"] = flag
        btn.config(text="❚❚  Pause" if flag else "▶  Play")
        if flag:
            tick()

    def tick():
        if not state["playing"]:
            return
        i, n = slider.get(), len(renderer.p["frames"])
        if i >= n - 1:
            set_playing(False)
            return
        goto(i + 1)
        state["after_id"] = root.after(max(1, int(1000 / (FPS * state["speed"]))), tick)

    def toggle():
        if renderer.p is None:
            return
        if not state["playing"] and slider.get() >= len(renderer.p["frames"]) - 1:
            goto(0)
        set_playing(not state["playing"])

    btn.config(command=toggle)

    def load_play(_=None):
        set_playing(False)
        idx = play_cb.current()
        if idx < 0:
            return
        try:
            df = source.load(state["plays"][idx][1])
            renderer.set_play(df)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            from tkinter import messagebox
            messagebox.showerror("Unable to load play", str(exc), parent=root)
            show_empty_state(f"Could not load play:\n{exc}")
            return
        state["selected"] = None
        update_player_choices()
        btn.config(state="normal")
        slider.config(state="normal")
        slider.config(to=len(renderer.p["frames"]) - 1)
        slider.set(0)
        render(0)

    def load_formation(_=None):
        set_playing(False)
        try:
            state["plays"] = source.plays(form_cb.get()) if form_cb.get() else []
        except (OSError, ValueError, KeyError) as exc:
            from tkinter import messagebox
            messagebox.showerror("Unable to list plays", str(exc), parent=root)
            state["plays"] = []
        play_cb.config(values=[lbl for lbl, _ in state["plays"]])
        if state["plays"]:
            play_cb.current(0)
            load_play()
        else:
            play_cb.set("")
            show_empty_state("No plays were found for this formation.")

    def on_click(ev):
        if ev.inaxes is None or ev.xdata is None:
            return
        i = slider.get()
        k = renderer.nearest(i, ev.xdata, ev.ydata)
        if k is None or k == -1:
            select_player(None)
        else:
            select_player(k)

    def on_player_selected(_=None):
        select_player(state["player_labels"].get(player_cb.get()))

    def on_speed(_=None):
        state["speed"] = float(speed_cb.get().rstrip("x"))

    def goto_snap():
        if renderer.p is not None:
            goto(renderer.p["snap_idx"])

    form_cb.bind("<<ComboboxSelected>>", load_formation)
    play_cb.bind("<<ComboboxSelected>>", load_play)
    player_cb.bind("<<ComboboxSelected>>", on_player_selected)
    speed_cb.bind("<<ComboboxSelected>>", on_speed)
    tactic_cb.bind("<<ComboboxSelected>>", on_tactic)
    canvas.mpl_connect("button_press_event", on_click)
    def close():
        state["playing"] = False
        if state["after_id"] is not None:
            try:
                root.after_cancel(state["after_id"])
            except tk.TclError:
                pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)

    if form_cb["values"]:
        form_cb.current(0)
        load_formation()
    else:
        show_empty_state("No formations are available in the selected data source.")
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source_group = ap.add_mutually_exclusive_group()
    source_group.add_argument("--data", help="folder with plays.csv + tracking files (defaults to project data/raw)")
    source_group.add_argument("--demo", action="store_true", help="use synthetic plays instead of real data")
    ap.add_argument("--snapshot", help="save a PNG of one frame and exit (no window)")
    ap.add_argument("--formation", help="formation for --snapshot")
    ap.add_argument("--variant", type=int, default=0, help="play index for --snapshot")
    ap.add_argument("--frame", type=int, default=None, help="frame index for --snapshot")
    ap.add_argument("--api", default=DEFAULT_API_URL,
                    help=f"backend API address for tactic rankings (default {DEFAULT_API_URL})")
    args = ap.parse_args()

    source = build_source(args.data, demo=args.demo)

    if args.snapshot:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure

        formations = source.formations()
        if not formations:
            raise SystemExit("no formations available in the selected data source")

        fm = args.formation or formations[0]
        if fm not in formations:
            raise SystemExit(f"formation '{fm}' not found; available: {', '.join(formations)}")

        plays = source.plays(fm)
        if not plays:
            raise SystemExit(f"no plays found for formation '{fm}'")
        if not 0 <= args.variant < len(plays):
            raise SystemExit(f"variant {args.variant} out of range for formation '{fm}' (0..{len(plays) - 1})")

        key = plays[args.variant][1]
        r = FieldRenderer(Figure(figsize=(10, 5.6), dpi=110))
        r.set_play(source.load(key))
        i = args.frame if args.frame is not None else r.p["snap_idx"]
        clamped = min(max(i, 0), len(r.p["frames"]) - 1)
        r.draw_frame(clamped)
        r.fig.savefig(args.snapshot)
        print("saved", args.snapshot)
        return

    run_gui(source, RankingsClient(args.api))


if __name__ == "__main__":
    main()
