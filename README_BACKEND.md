# Backend: NFL Center Pass-Protection Fit Ranker

The backend turns the NFL Big Data Bowl data in `data/raw/` into a suitability % for every
qualifying center, for each pass-protection tactic, and serves the rankings through a Flask
API. The formation viewer (the UI) gets its rankings from that API, and the command-line
tool calls the same service function the API uses, so every screen shows the same numbers.

```
data/raw/*.csv ──► preprocess (once) ──► data/processed/ ──► service + Flask API ──► formation viewer
                   per-center stats       committed to git     scores and ranks        / CLI / browser
                   and benchmarks                              on every request
```

Python does every calculation at runtime: no result is typed into the code. The slow part
(reading about 800 MB of CSVs) runs once in `preprocess`; scoring and ranking run again on
every API request, and the result is not stored.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Tested with Python 3.14, pandas 3.0, Flask 3.1 and matplotlib 3.11. Everything runs from the
repo root; all paths are relative to it, so it works on Windows, macOS and Linux.

## Commands

| What | Command | Notes |
|---|---|---|
| Run the API | `python app.py` | http://localhost:5001. `--port`, `--debug` available |
| Run the UI | `python -m backend.formation_viewer` | needs the API running for rankings |
| Print / export rankings | `python -m backend.cli --all` or `--tactic stunt_twist` | top 15 per tactic, also written to `outputs/<tactic>_top15.csv` and `.json` |
| Rebuild processed data | `python -m backend.preprocess` | about 17 s with tracking. Only needed after changing data or settings |
| Rebuild without tracking | `python -m backend.preprocess --no-tracking` | the fallback path, about 2 s |
| Run the tests | `python -m pytest` | about 4 s |
| Check the raw data | `python -m backend.inspect_data` | labels, snap counts, event tags; read-only |

After re-running `preprocess`, restart `python app.py`: the API reads the processed files
once, on its first request.

## Test it yourself

1. **Automated tests:** `python -m pytest` should end with every test passing.
2. **API:** run `python app.py`, then open these in a browser:
   - http://localhost:5001/api/health: `"status": "ok"`, whether tracking was used, when the data was built
   - http://localhost:5001/api/tactics: the six tactics
   - http://localhost:5001/api/rankings?tactic=dropback: the top 15 centers with their attributes
   - http://localhost:5001/api/rankings?tactic=nope: a 400 with an error message
3. **UI:** with the API still running, in a second terminal run `python -m backend.formation_viewer`.
   - Choose a **TACTIC ANALYSIS**: the right-hand panel lists the top 15, computed by the
     backend at that moment, and where this play's center ranks.
   - Click the center on the field, or choose the player marked `· C` under **PLAYER**: his
     rank, suitability %, confidence and each attribute's value, score and weight.
   - Stop the API (Ctrl+C in its terminal) and choose a tactic again: the panel explains how
     to start it.
4. **CLI:** `python -m backend.cli --all` prints six tables and writes them to `outputs/`.

## API

All responses are JSON and sent with `Cache-Control: no-store`. CORS allows the Vite dev
server (`localhost:5173` / `4173`) in case a web front end is added later.

| Endpoint | Returns |
|---|---|
| `GET /api/tactics` | `[{key, name, description, attributeCount}]` for the enabled tactics |
| `GET /api/rankings?tactic=<key>&limit=<n>` | ranked centers for one tactic; `limit` 1-50, default 15 |
| `GET /api/health` | `status`, `trackingUsed`, `generatedAt`, `qualifyingCenters`, `enabledTactics` |

Errors are `{"error": "..."}`: **400** for a missing, unknown or disabled tactic or a bad
`limit`, **503** when `data/processed/` is missing, **404** for an unknown `/api/...` path.

`/api/rankings` response (one player shown):

```json
{
  "tactic": "stunt_twist",
  "tacticName": "Stunt & twist handling",
  "trackingUsed": false,
  "columns": [
    {"key": "sw_loss_rate", "label": "Switch-block loss rate", "weight": 0.4, "better": "lower", "format": "pct"},
    {"key": "weight_lb", "label": "Weight", "weight": 0.1, "better": "target", "format": "lb", "target": 305}
  ],
  "players": [{
    "rank": 1, "nflId": 0, "name": "", "team": "", "age": 0, "suitability": 0.0,
    "confidence": "High", "tacticSnaps": 0, "baseSnaps": 0,
    "attributes": {
      "sw_loss_rate": {"value": 0.0, "display": "0.0%", "score": 0, "ideal": 0.0, "floor": 0.0},
      "weight_lb": {"value": 0, "display": "0 lb", "score": 0, "ideal": 305, "floor": null}
    },
    "topStrength": "sw_loss_rate", "biggestConcern": "weight_lb"
  }]
}
```

- `trackingUsed`: whether *this tactic's* ranking used tracking data (its filter or an attribute).
- `columns`: the active attributes in importance order. `weight` is a fraction; `better` is
  `lower`, `higher` or `target`, and target attributes also carry `target`.
- `value` is the raw number (rates are fractions, so 0.031 is 3.1%), `display` is the text
  to show, `score` is the attribute score as a whole number from 0 to 100.
- `ideal` / `floor` are the benchmarks the score was measured against. For a target
  attribute, `ideal` is the target and `floor` is `null`.
- `age` is `null` when the player's birth date is missing.

## How every number is calculated

Names in `CAPS` are settings in `backend/config.py`; the tactics live in `backend/tactics.py`.

### 1. Data and player pool
- `data_loader.py` is the only pipeline module that reads the raw CSVs. It loads only the
  whitelisted columns (`WHITELIST`) and stops with a clear error if one is missing.
- **Base snap:** a scouting row with `pff_role` = `Pass Block` and `pff_positionLinedUp` = `C`,
  joined to its play.
- A center **qualifies** with at least `MIN_BASE_SNAPS` (150) base snaps.
- **Team** is his most frequent `possessionTeam` on base snaps. **Age** is whole years on
  `AGE_AS_OF` (2021-09-01, the start of the season the data covers). **Height** `6-3` becomes
  75 inches.

### 2. Per-snap outcomes
| Outcome | Counts when |
|---|---|
| loss | beaten, hit, hurry or sack allowed |
| pressure | hit, hurry or sack allowed |
| sack | sack allowed |
| penalty | his `nflId` is one of the play's `foulNFLId1-3` |

Blank allowed/beaten flags count as 0. `n_rushers` is the number of `Pass Rush` rows on the play.

### 3. Rates, with shrinkage
Small samples are pulled toward a prior so a handful of snaps cannot produce an extreme rate:

- **Overall rate** = (events + `K_OVERALL` × league rate) / (base snaps + `K_OVERALL`), with
  `K_OVERALL` = 50. The league rate is pooled over every qualifying center's base snaps
  (total events ÷ total snaps).
- **Tactic rate** = (tactic events + `K_TACTIC` × his overall rate) / (tactic snaps + `K_TACTIC`),
  with `K_TACTIC` = 20. With no snaps for that tactic, it equals his overall rate.
- **Penalty rate** is overall only.

Example (made-up numbers): 10 losses in 100 snaps, league rate 5%:
(10 + 50 × 0.05) / (100 + 50) = 8.3%.

### 4. Tracking values (only when tracking files exist)
Read from the center's own rows on his base snaps, at 10 frames per second:

- **Snap frame:** `ball_snap`, or `autoevent_ballsnap` if the manual tag is missing.
- **End of the pocket:** the first tag after the snap among `pass_forward` (or
  `autoevent_passforward` if the manual tag is missing), `qb_sack` / `qb_strip_sack`, and
  `run` (a QB scramble).
- **time_to_event** = (end frame − snap frame) / 10 seconds.
- **lateral_speed** = sum of |change in y| over the 20 frames after the snap ÷ 2.0 s (yd/s),
  averaged over the tactic's snaps. Snaps without all 20 frames are left out.
- **depth_lost_3s** = (x at the snap − x 30 frames later) × (+1 if `playDirection` is right,
  −1 if left), so yards moved back toward his own end zone count as positive. Averaged over
  the tactic's snaps.

### 5. Benchmarks (`benchmarks.json`)
Percentiles of the qualifying centers' values, using numpy's linear interpolation:

| Better | Ideal | Floor |
|---|---|---|
| lower | 10th percentile | 90th percentile |
| higher | 90th percentile | 10th percentile |

### 6. Scores, suitability and ranking
| Better | Attribute score (0 to 1) |
|---|---|
| lower | clip((floor − x) / (floor − ideal), 0, 1) |
| higher | clip((x − floor) / (ideal − floor), 0, 1) |
| target | 1 within ±5 lb of the target, then (25 − distance) / 20, down to 0 at ±25 lb |

If `ideal == floor`, or the center has no value (for example, no tracked snaps for that
tactic), the score is 0.5 (neutral).

- **Suitability %** = 100 × Σ (weight × score), rounded half up to 1 decimal. The sum uses the
  unrounded scores; the `score` shown per attribute is rounded separately.
- **Rank:** suitability, highest first; ties go to more tactic snaps, then more base snaps,
  then the lower `nflId`.
- **topStrength** is the attribute with the largest weight × score. **biggestConcern** is the
  one with the largest weight × (1 − score).
- **Confidence** from tactic snaps: High ≥ 60, Medium 25-59, Low < 25.

## Tactics
Weights are shares of the suitability score. `backend/tactics.py` is the source of truth.

| Tactic | Snaps that count | Attributes in importance order (weight) |
|---|---|---|
| `dropback` | block type PP, no play action, traditional dropback | loss 35, pressure 25, sack 15, weight (target 310 lb) 15, penalty 10 |
| `play_action` | play action | PA loss 35, PA pressure 25, overall loss 15, PA sack 10, weight (305) 10, penalty 5 |
| `rollout` | block type PR, or a designed rollout (not scrambles) | rollout loss 35, rollout pressure 20, lateral speed 20, overall loss 10, weight (300) 10, penalty 5 |
| `stunt_twist` | block type SW (switch block) | SW loss 40, SW pressure 25, overall loss 15, penalty 10, weight (305) 10 |
| `blitz` | 5 or more pass rushers | loss 35, pressure 25, sack 15, weight (315) 15, overall loss 10 |
| `long_dev` | time to throw, sack or scramble ≥ 3.0 s (needs tracking) | loss 30, pressure 25, depth lost at 3 s 20, sack 10, weight (312) 10, penalty 5 |

**Without tracking files**, `long_dev` is disabled (not listed and a 400 if requested),
`lateral_speed` is dropped from `rollout`, and the remaining weights are rescaled
proportionally so they still sum to 1. `preprocess --no-tracking` shows this path.

## Files

| File | Role |
|---|---|
| `backend/config.py` | every path, column whitelist, label, threshold and constant |
| `backend/tactics.py` | the six tactics: filters, weighted attributes, tracking rules |
| `backend/data_loader.py` | reads the raw CSVs (whitelisted columns only) |
| `backend/features.py` | snaps, outcome flags, shrunk rates, benchmarks |
| `backend/tracking_features.py` | time_to_event, lateral_speed, depth_lost_3s from tracking chunks |
| `backend/preprocess.py` | writes `data/processed/centers_stats.csv`, `benchmarks.json`, `meta.json` |
| `backend/scoring.py` | attribute scores, suitability, ranking, confidence |
| `backend/formatting.py` | display text and JSON-safe conversion |
| `backend/service.py` | `get_tactics()`, `get_rankings()`; what Flask and the CLI call |
| `backend/api.py` | Flask blueprint for `/api/...` |
| `app.py` | the Flask app (also serves a built web UI from `frontend/dist` if one exists) |
| `backend/cli.py` | prints and exports the top 15 per tactic |
| `backend/formation_viewer.py` | the desktop UI; tactic rankings come from the API |
| `backend/inspect_data.py` | read-only data report |

## Tests

| File | Covers |
|---|---|
| `test_tactics.py` | weights sum to 1 (with and without tracking), each filter keeps only its snaps |
| `test_features.py` | shrinkage against hand calculations, flags, blank flags and foul matching, age, team, benchmarks |
| `test_scoring.py` | lower / higher / target scores, ideal == floor, suitability in 0-100, ranks without gaps, tie-breaks |
| `test_service.py` | JSON-safe output (no numpy, no NaN), contract fields, limit and tactic errors, no-tracking path |
| `test_api.py` | endpoints, 400 / 503 errors, `no-store`, CORS |
| `test_data_loader.py` | missing whitelisted column error, only whitelisted columns loaded, date and height parsing |
| `test_formation_viewer.py` | the viewer's ranking text, unranked players, unreachable-API message |
| `test_integration.py` | the viewer's client against a real Flask server and the committed processed data |

Unit tests use small hand-built tables (`tests/conftest.py`), not the real data.

## Known limits
- Rollouts and switch blocks are rare in the data, so most centers have few of those snaps
  and show Low confidence for those tactics; their rates lean on each center's overall rate.
- `lateral_speed` and `depth_lost_3s` are plain averages, not shrunk.
- The viewer reads the raw CSVs itself to draw plays (it needs columns such as team, jersey
  number and speed). The ranking pipeline reads them only through `data_loader.py`.
