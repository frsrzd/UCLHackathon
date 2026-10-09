# NFL Center Pass-Protection Fit Ranker

Ranks NFL centers by suitability % for a chosen pass-protection tactic, using NFL Big Data Bowl data.
Python (pandas) backend, Flask API, React (Vite) frontend.

## Setup (after cloning)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m backend.inspect_data      # sanity-check the raw data
```

The raw data is already in `data/raw/` (CSV files + `tracking/`, one file per game).
Generated files go in `data/processed/` and `outputs/`; they are not committed, so run the
preprocess step locally once it exists.

## Layout

```
backend/        pandas pipeline, scoring, service layer (+ Flask blueprint)
data/raw/       source CSVs (read-only, never modified by code)
data/processed/ generated: centers_stats.csv, benchmarks.json, meta.json
outputs/        generated: CLI top-15 CSV/JSON per tactic
frontend/       React (Vite) app
```

## Formation viewer

The optional desktop viewer animates real plays and lets you inspect player
movement and available tactic metrics. Install dependencies from
`requirements.txt`, then run it from the project root:

```bash
python -m backend.formation_viewer
```

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
