import pytest

from app import create_app
from backend import service
from tests.conftest import make_processed


@pytest.fixture
def client(monkeypatch):
    """Flask test client serving hand-built processed data."""
    data = make_processed(tracking_used=True)
    monkeypatch.setattr(service, "load_processed", lambda: data)
    return create_app().test_client()


def test_tactics_endpoint(client):
    response = client.get("/api/tactics")

    assert response.status_code == 200
    assert [t["key"] for t in response.get_json()][0] == "dropback"


def test_rankings_default_limit_and_no_store(client):
    response = client.get("/api/rankings?tactic=dropback")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.get_json()["players"]) == 6        # 6 made-up centers < 15


def test_rankings_limit(client):
    assert len(client.get("/api/rankings?tactic=blitz&limit=2").get_json()["players"]) == 2


@pytest.mark.parametrize("query", ["tactic=nope", "", "tactic=dropback&limit=0",
                                   "tactic=dropback&limit=51", "tactic=dropback&limit=ten"])
def test_bad_requests_get_400_with_an_error_message(client, query):
    response = client.get(f"/api/rankings?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]


def test_missing_processed_data_gets_503(monkeypatch):
    def missing():
        raise service.ProcessedDataMissing("run python -m backend.preprocess")
    monkeypatch.setattr(service, "load_processed", missing)
    client = create_app().test_client()

    for path in ["/api/tactics", "/api/rankings?tactic=dropback", "/api/health"]:
        response = client.get(path)
        assert response.status_code == 503
        assert "backend.preprocess" in response.get_json()["error"]


def test_cors_allows_the_vite_dev_server(client):
    response = client.get("/api/tactics", headers={"Origin": "http://localhost:5173"})
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
