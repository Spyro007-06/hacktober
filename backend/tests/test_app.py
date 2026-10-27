import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import create_app


def test_network_guard_blocks_real_httpx_requests():
    """The guard must stop real requests. 203.0.113.7 is a reserved TEST-NET
    address, so even a failing guard could not reach a real service."""
    import asyncio

    import httpx

    async def go():
        async with httpx.AsyncClient(timeout=2) as c:
            await c.get("http://203.0.113.7/")

    with pytest.raises(AssertionError, match="real network request"):
        asyncio.run(go())

    with pytest.raises(AssertionError, match="real network request"):
        httpx.get("http://203.0.113.7/", timeout=2)


def test_network_guard_also_blocks_httpx2_which_huggingface_hub_uses():
    """httpx2 is a separate library from httpx; the guard must cover it too."""
    import asyncio

    import httpx2

    from .conftest import NETWORK_ATTEMPTS

    async def go():
        async with httpx2.AsyncClient(timeout=2) as c:
            await c.get("http://203.0.113.7/")

    with pytest.raises(AssertionError, match="real network request"):
        asyncio.run(go())
    with pytest.raises(AssertionError, match="real network request"):
        httpx2.get("http://203.0.113.7/", timeout=2)
    assert NETWORK_ATTEMPTS == ["203.0.113.7", "203.0.113.7"]


def test_startup_and_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_mode": "online", "model": "unconfigured"}


def test_health_reports_configured_model(settings):
    s = settings.model_copy(update={"gemini_model": "some-model-id"})
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").json()["model"] == "some-model-id"


def test_health_offline_mode(settings):
    s = settings.model_copy(update={"model_mode": "offline", "ollama_model": "tag"})
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").json() == {
            "status": "ok", "model_mode": "offline", "model": "tag"}


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "Resource not found."}}


def test_startup_creates_database_and_uploads(client, settings):
    assert settings.db_path.exists()
    assert settings.uploads_dir.is_dir()


def test_startup_warns_about_unverified_departments(settings, caplog):
    with caplog.at_level("WARNING", logger="kural"):
        with TestClient(create_app(settings)):
            pass
    assert any("UNVERIFIED" in r.getMessage() for r in caplog.records)


def test_startup_fails_fast_on_invalid_departments(settings):
    (settings.data_dir / "departments.json").write_text('{"departments": [{"id": "x"}]}')
    with pytest.raises(ValidationError):
        with TestClient(create_app(settings)):
            pass


def test_startup_fails_fast_on_missing_rules(settings):
    (settings.data_dir / "rules.json").unlink()
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(settings)):
            pass
