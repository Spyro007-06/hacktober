import sys

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import AppError
from backend.main import create_app
from backend.models import Session
from backend.services.uploads import resolve_photo, save_photos, validate_photos
from .conftest import make_image


def post(client, files=(), **over):
    data = {"text": "Streetlight is dead", "language": "en"}
    data.update(over)
    return client.post("/api/sessions", data=data, files=list(files))


def code(r):
    return r.json()["error"]["code"]


def png(name="a.png"):
    return ("photos", (name, make_image(), "image/png"))


def test_missing_text_is_bad_input(client):
    r = client.post("/api/sessions", data={"language": "en"})
    assert r.status_code == 400 and code(r) == "BAD_INPUT"


def test_blank_text_is_bad_input(client):
    assert post(client, text="   ").status_code == 400


def test_bad_language_is_bad_input(client):
    assert post(client, language="fr").status_code == 400


def test_bad_lat_is_bad_input(client):
    assert post(client, lat="123").status_code == 400


def test_too_many_photos(client):
    r = post(client, files=[png(f"{i}.png") for i in range(4)])
    assert r.status_code == 400 and code(r) == "BAD_INPUT"


def test_unsupported_file_rejected_by_content_not_name(client):
    r = post(client, files=[("photos", ("evil.png", b"<?php echo 1;", "image/png"))])
    assert r.status_code == 400


def test_gif_rejected(client):
    assert post(client, files=[("photos", ("a.gif", make_image("GIF"), "image/gif"))]).status_code == 400


def test_oversized_photo_rejected(settings):
    s = settings.model_copy(update={"max_photo_mb": 1})
    with TestClient(create_app(s)) as c:
        big = make_image() + b"0" * (1024 * 1024 + 1)
        r = c.post("/api/sessions", data={"text": "x", "language": "en"},
                   files=[("photos", ("a.png", big, "image/png"))])
        assert r.status_code == 400


def test_valid_input_without_provider_config_is_503(client):
    # The test settings have no GEMINI_API_KEY/GEMINI_MODEL: a clear config error.
    r = post(client, files=[png()])
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"
    assert "GEMINI_API_KEY" in r.json()["error"]["message"]


def test_valid_text_only_without_provider_config_is_503(client):
    assert post(client).status_code == 503


def test_nothing_stored_on_503(client, settings):
    post(client, files=[png()])
    assert list(settings.uploads_dir.iterdir()) == []


def test_get_session_not_found(client):
    r = client.get("/api/sessions/s_missing")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"


def test_get_session_returns_stored_session(client):
    s = Session(id="s_abc", transcript="t", language="ta", status="needs_info")
    client.app.state.db.save_session(s)
    r = client.get("/api/sessions/s_abc")
    assert r.status_code == 200 and Session.model_validate(r.json()) == s


def test_answers_unknown_session_404(client):
    r = client.post("/api/sessions/s_x/answers", json={"answers": {"location": "x"}})
    assert r.status_code == 404


def test_answers_validation(client):
    client.app.state.db.save_session(
        Session(id="s_1", transcript="t", language="en", status="needs_info"))
    assert client.post("/api/sessions/s_1/answers", json={}).status_code == 400
    assert client.post("/api/sessions/s_1/answers", json={"answers": {}}).status_code == 400
    # Valid answers reach the provider step, which is unconfigured here (503).
    r = client.post("/api/sessions/s_1/answers", json={"answers": {"location": "x"}})
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"


# -- upload helpers ---------------------------------------------------------
def test_validate_photos_accepts_formats():
    out = validate_photos([make_image("PNG"), make_image("JPEG"), make_image("WEBP")], 3, 10**6)
    assert [e for _, e in out] == ["png", "jpg", "webp"]


def test_validate_photos_rejects_empty_and_count():
    with pytest.raises(AppError):
        validate_photos([b""], 3, 10**6)
    with pytest.raises(AppError):
        validate_photos([make_image()] * 2, 1, 10**6)


def test_save_photos_uses_generated_names(tmp_path):
    names = save_photos(tmp_path, "s_1", [(make_image(), "png")])
    assert names[0].startswith("s_1/") and names[0].endswith(".png")
    assert resolve_photo(tmp_path, names[0]).read_bytes() == make_image()


WINDOWS_PATH = pytest.param("C:\\Windows\\win.ini", marks=pytest.mark.skipif(
    sys.platform != "win32", reason="a backslash is only a path separator on Windows"))


@pytest.mark.parametrize("bad", ["../secret.txt", "s_1/../../x", "/etc/passwd", WINDOWS_PATH])
def test_resolve_photo_blocks_path_traversal(tmp_path, bad):
    with pytest.raises(AppError):
        resolve_photo(tmp_path, bad)


def test_settings_resolves_relative_data_dir():
    s = Settings(_env_file=None, data_dir="./data")
    assert s.data_dir.is_absolute() and s.data_dir.name == "data"
    assert s.data_dir.parent.name == "backend"
