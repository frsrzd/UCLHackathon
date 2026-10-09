# NFL Center Pass-Protection Fit Ranker

Ranks NFL centers by suitability % for a chosen pass-protection tactic, using NFL Big Data Bowl data.
Python (pandas) backend, Flask API, and a desktop formation viewer (Tk + matplotlib) as the UI.

## Setup (after cloning)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m backend.inspect_data      # sanity-check the raw data
```

The raw data is already in `data/raw/` (CSV files + `tracking/`, one file per game).
`data/processed/` is committed, so the API works straight after cloning; rebuild it with
`python -m backend.preprocess` after changing the data or settings. `outputs/` (CLI exports)
is not committed.

## Run it

Two terminals, both at the project root with the virtual environment active:

```bash
python app.py                        # 1. backend API on http://localhost:5001
python -m backend.formation_viewer   # 2. the UI: tactic rankings come from the API
```

In the viewer, pick a **tactic** to see its top 15 centers, scored and ranked by the backend
at that moment; click a **center** on the field (or pick him under PLAYER) for his rank,
suitability % and attribute breakdown. Run every test with `python -m pytest`.

## Layout

```
backend/        pandas pipeline, scoring, service layer, Flask blueprint, formation viewer
app.py          Flask app: the API under /api (python app.py)
data/raw/       source CSVs (read-only, never modified by code)
data/processed/ generated and committed: centers_stats.csv, benchmarks.json, meta.json
outputs/        generated: CLI top-15 CSV/JSON per tactic
tests/          pytest suite
```

## Formation viewer

The desktop viewer animates real plays, lets you inspect player movement, and shows
the backend's tactic rankings. Install dependencies from `requirements.txt`, start the
API (`python app.py`), then run it from the project root:

```bash
python -m backend.formation_viewer
```

Without the API running, plays still animate and the tactic panel explains how to start
it. Use `--api http://host:port` if the API runs somewhere else.

By default, it loads the Big Data Bowl files from `data/raw/`. To use synthetic
plays without loading the dataset, run:

```bash
python -m backend.formation_viewer --demo
```

Save a frame without opening a window with:

```bash
python -m backend.formation_viewer --snapshot outputs/formation.png --formation SHOTGUN
```

Use `--data path/to/bdb` to load a different Big Data Bowl data folder. The viewer
reads the CSV and tracking files without modifying them.

## Workflow

Work on your own branch (`backend`, `api`, `frontend`) and merge into `main` via pull request.
