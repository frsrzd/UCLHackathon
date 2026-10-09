"""
Minimal Flask app for local development.

    python app.py            ->  http://localhost:5001
    python app.py --debug    (auto-reloads when the code changes)

  /api/...  the backend API (backend/api.py)
  /         the built React app from frontend/dist, if it has been built
            (npm run build in frontend/); otherwise a JSON list of the API endpoints

CORS allows the Vite dev server origins in config.CORS_ORIGINS, so the React app
can also run on its own with `npm run dev` and call this API directly.
"""
import argparse

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend import config, service
from backend.api import bp as api_bp

ENDPOINTS = {
    "GET /api/tactics": "enabled tactics: key, name, description, attributeCount",
    "GET /api/rankings?tactic=<key>&limit=<1-50>": "ranked centers for one tactic (default 15)",
    "GET /api/health": "processed data status",
}


def create_app():
    app = Flask(__name__, static_folder=None)   # no /static route: the UI build owns paths
    app.json.sort_keys = False
    app.register_blueprint(api_bp)
    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        """Serve the built UI (falling back to index.html for client-side routes)."""
        dist = config.FRONTEND_DIST_DIR
        if path.startswith("api/"):
            return jsonify(error=f"Unknown API endpoint '/{path}'."), 404
        if not (dist / "index.html").is_file():
            index = {"service": "NFL Center Pass-Protection Fit Ranker API",
                     "endpoints": ENDPOINTS,
                     "frontend": "No UI build found at frontend/dist. Run `npm run dev` "
                                 "in frontend/, or `npm run build` to serve it here."}
            return jsonify(index), 200 if path == "" else 404
        if path and (dist / path).is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the API (and the built UI) locally.")
    parser.add_argument("--host", default=config.API_HOST)
    parser.add_argument("--port", type=int, default=config.API_PORT)
    parser.add_argument("--debug", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args()

    try:
        _, _, meta = service.load_processed()
        print(f"Processed data OK: built {meta['generatedAt']}, "
              f"tracking used: {meta['trackingUsed']}")
    except service.ProcessedDataMissing as err:
        print(f"WARNING: {err} The API will answer 503 until then.")
    ui = "found" if (config.FRONTEND_DIST_DIR / "index.html").is_file() else "not built"
    print(f"UI build (frontend/dist): {ui}")
    create_app().run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
