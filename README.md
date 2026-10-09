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

## Workflow

Work on your own branch (`backend`, `api`, `frontend`) and merge into `main` via pull request.
