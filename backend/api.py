"""
Flask Blueprint exposing the service layer as JSON under /api.

  GET /api/tactics                            enabled tactics
  GET /api/rankings?tactic=<key>&limit=<n>    ranked centers (limit 1-50, default 15)
  GET /api/health                             processed data loaded? tracking used? built when?

Every rankings request scores and ranks the centers afresh (service.get_rankings);
only the processed input files are kept in memory between requests. Responses are
sent with Cache-Control: no-store so the browser never reuses an old ranking.

Errors are JSON {"error": "..."}:
  400  missing, unknown or disabled tactic; limit not a whole number from 1 to 50
  503  processed files missing (run `python -m backend.preprocess`)
"""
import json

from flask import Blueprint, Response, request

from backend import config, service

bp = Blueprint("api", __name__, url_prefix="/api")


def _json(payload, status=200):
    """JSON response that keeps keys in the order they were built (so attributes
    stay in importance order) whatever the host app's JSON settings are."""
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    response = Response(body, status=status, mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.errorhandler(service.ProcessedDataMissing)
def _processed_missing(err):
    return _json({"error": str(err)}, 503)


@bp.errorhandler(service.UnknownTactic)
@bp.errorhandler(service.InvalidLimit)
def _bad_request(err):
    return _json({"error": str(err)}, 400)


def _parse_limit(raw):
    """The limit query parameter as an int (default DEFAULT_LIMIT); range is checked
    by the service."""
    if raw is None or raw.strip() == "":
        return config.DEFAULT_LIMIT
    try:
        return int(raw)
    except ValueError:
        raise service.InvalidLimit(f"limit must be a whole number from {config.MIN_LIMIT} "
                                   f"to {config.MAX_LIMIT}, got {raw!r}") from None


@bp.get("/tactics")
def tactics():
    return _json(service.get_tactics())


@bp.get("/rankings")
def rankings():
    tactic = request.args.get("tactic", "").strip()
    if not tactic:
        valid = ", ".join(t["key"] for t in service.get_tactics())
        return _json({"error": f"Missing query parameter 'tactic'. Valid tactics: {valid}."},
                     400)
    return _json(service.get_rankings(tactic, _parse_limit(request.args.get("limit"))))


@bp.get("/health")
def health():
    _, _, meta = service.load_processed()
    return _json({
        "status": "ok",
        "trackingUsed": meta["trackingUsed"],
        "generatedAt": meta["generatedAt"],
        "qualifyingCenters": meta["rowCounts"]["qualifyingCenters"],
        "enabledTactics": service.enabled_keys(meta),
    })
