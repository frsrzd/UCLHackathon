"""
End to end: the viewer's API client -> a real Flask server (app.py) -> the backend
service, using the committed data/processed/ files.
"""
import threading

import pytest
from werkzeug.serving import make_server

from app import create_app
from backend import service
from backend.formation_viewer import BackendUnavailable, RankingsClient
from backend.tactics import active_attributes, TACTICS


@pytest.fixture(scope="module")
def api_url():
    service.reload()                                 # read the real processed files
    server = make_server("127.0.0.1", 0, create_app())   # port 0: any free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_viewer_gets_a_fresh_ranking_through_flask(api_url):
    ranking = RankingsClient(api_url).rankings("dropback", limit=15)

    assert ranking["tactic"] == "dropback"
    assert [p["rank"] for p in ranking["players"]] == list(range(1, 16))
    expected = [a.key for a in active_attributes(TACTICS["dropback"], tracking_used=True)]
    assert [c["key"] for c in ranking["columns"]] == expected
    suits = [p["suitability"] for p in ranking["players"]]
    assert suits == sorted(suits, reverse=True)


def test_api_errors_reach_the_viewer_as_readable_messages(api_url):
    with pytest.raises(BackendUnavailable, match="Unknown tactic 'nope'"):
        RankingsClient(api_url).rankings("nope")
