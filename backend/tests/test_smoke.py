"""Smoke tests: risk classification (incl. the docked-spacecraft regression) and the API app."""

from fastapi.testclient import TestClient

from app.main import app
from app.risk import classify, is_reportable


def test_docked_spacecraft_are_not_high_risk() -> None:
    # ISS + docked vehicle: ~0 km apart, ~0 relative speed. Must not be flagged "high".
    assert classify(0.0, 0.0) == "co-orbiting"


def test_genuine_close_approach_is_high_risk() -> None:
    assert classify(0.5, 7.5) == "high"
    assert classify(3.0, 7.5) == "moderate"
    assert classify(9.0, 7.5) == "low"


def test_reportable_threshold() -> None:
    assert is_reportable(9.99)
    assert not is_reportable(10.0)


def test_health_endpoint() -> None:
    # No `with` block: skips the lifespan, so no network call to CelesTrak.
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
