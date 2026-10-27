import io
import re
import sys
import threading
import urllib.request

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from backend.main import create_app
from backend.services import pdf as pdf_mod
from backend.services.pdf import FONT_PATH, _is_bundled_font, make_fetcher, render_pdf
from backend.services.uploads import save_photos
from .conftest import draft_body, make_image, seed_session
from .test_drafts_api import dept, write_departments

TAMIL = "கொடி கோட்டை கௌரி க்ஷ ஸ்ரீ ஜ ஹ ஃ ௧௨௩ தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை."
UNKNOWN = "a1b2c3d4"


# -- helpers -------------------------------------------------------------------------
def reader(data: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(data))


def text(rd: PdfReader) -> str:
    return "\n".join(p.extract_text() for p in rd.pages)


def font_names(rd: PdfReader) -> set[str]:
    names = set()
    for page in rd.pages:
        for ref in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
            names.add(str(ref.get_object().get("/BaseFont")))
    return names


def image_objects(rd: PdfReader) -> list:
    """Unique image XObjects. pypdf lists a document's images on every page's
    resources, so count by object id, not per page."""
    found = {}
    for page in rd.pages:
        for ref in (page.get("/Resources", {}).get("/XObject", {}) or {}).values():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image":
                found[ref.idnum] = obj
    return list(found.values())


def jpeg_bytes(size=(2400, 1800), orientation=None) -> bytes:
    img = Image.new("RGB", size, (200, 40, 40))
    buf = io.BytesIO()
    exif = img.getexif()
    if orientation:
        exif[0x0112] = orientation
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def make(client, rule_id="R2", photos=0, photo_blobs=None, complainant=None, **ext):
    """Seed a session (optionally with stored photos) and create its draft."""
    s = seed_session(client, rule_id=rule_id, **ext)
    blobs = photo_blobs or [jpeg_bytes((2400 + 50 * i, 1800)) for i in range(photos)]
    if blobs:
        names = save_photos(client.app.state.settings.uploads_dir, s.id, [(b, "jpg") for b in blobs])
        client.app.state.db.save_session(s.model_copy(update={"photo_paths": names}))
    body = draft_body(s.id, **({"complainant": complainant} if complainant else {}))
    r = client.post("/api/drafts", json=body)
    assert r.status_code == 200, r.text
    return s, r.json()


def get_pdf(client, draft_id):
    return client.get(f"/api/drafts/{draft_id}/pdf")


# -- the endpoint --------------------------------------------------------------------
def test_pdf_is_a_valid_pdf_document(client):
    _, d = make(client)
    r = get_pdf(client, d["draft_id"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and r.content.rstrip().endswith(b"%%EOF")
    rd = reader(r.content)
    assert len(rd.pages) >= 1 and not rd.is_encrypted


def test_response_headers_follow_the_prd_and_protect_personal_data(client):
    _, d = make(client)
    h = get_pdf(client, d["draft_id"]).headers
    assert h["content-disposition"] == f'attachment; filename="kural_local_body_{d["draft_id"]}.pdf"'
    assert h["cache-control"] == "no-store" and h["x-content-type-options"] == "nosniff"


def test_filename_uses_the_effective_route(client):
    s = seed_session(client, rule_id="R2")
    d = client.post("/api/drafts", json=draft_body(s.id, route_override="cm_helpline")).json()
    assert f"kural_cm_helpline_{d['draft_id']}.pdf" in get_pdf(client, d["draft_id"]).headers["content-disposition"]
    _, rti = make(client, rule_id="R1")
    assert f"kural_rti_{rti['draft_id']}.pdf" in get_pdf(client, rti["draft_id"]).headers["content-disposition"]


def test_unknown_draft_is_404(client):
    r = get_pdf(client, "d_missing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_pdf_has_the_bilingual_content_and_unverified_warnings(client):
    _, d = make(client, summary_ta=TAMIL, summary_en="Light near the library is dead.")
    t = text(reader(get_pdf(client, d["draft_id"]).content))
    for expected in ("Complaint draft", "Complainant", "R. Priya", "14 Gandhi Street",
                     "Light near the library is dead.", "DEMO DATA", "has not been verified"):
        assert expected in t, expected
    assert "புகார்" in t
    assert sum(1 for ch in t if "\u0b80" <= ch <= "\u0bff") > 100  # a lot of Tamil, not tofu/blank
    assert "within" not in t  # no response time from unverified data


def test_verified_department_pdf_states_its_response_days_and_has_no_demo_banner(settings):
    write_departments(settings, [dept("test-verified", ["local_body"], ["streetlight"], verified=True, days=7)])
    with TestClient(create_app(settings)) as c:
        _, d = make(c)
        t = text(reader(get_pdf(c, d["draft_id"]).content))
    assert "within 7 days" in t and "DEMO DATA" not in t


def test_rti_pdf_lists_the_requested_information(client):
    _, d = make(client, rule_id="R1", wants_records=True, requested_info=["Road repair budget"])
    t = text(reader(get_pdf(client, d["draft_id"]).content))
    assert "Information requested" in t and "Road repair budget" in t


def test_pdf_reflects_edits_made_through_patch(client):
    _, d = make(client)
    client.patch(f"/api/drafts/{d['draft_id']}", json={"fields": {"summary_en": "Edited for the PDF test."},
                                                       "complainant": {"phone": "9000000000"}})
    t = text(reader(get_pdf(client, d["draft_id"]).content))
    assert "Edited for the PDF test." in t and "9000000000" in t


# -- fonts and Tamil -------------------------------------------------------------------
def test_noto_sans_tamil_is_embedded_and_nothing_else(client):
    _, d = make(client, summary_ta=TAMIL)
    names = font_names(reader(get_pdf(client, d["draft_id"]).content))
    assert names and all("Noto-Sans-Tamil" in n for n in names), names  # no Nirmala/Arial fallback
    assert any(n.endswith("Noto-Sans-Tamil-Bold") for n in names)  # bold instance made from the variable font


def test_the_bundled_font_file_is_the_verified_one():
    import hashlib
    assert hashlib.sha256(FONT_PATH.read_bytes()).hexdigest() == \
        "aa3a9b321f4b0bb2c40203ffbde9af89713227866e0e13f76e5b9eeea727cf88"
    assert FONT_PATH.with_name("OFL.txt").is_file() and FONT_PATH.with_name("SOURCE.md").is_file()


# -- evidence page -----------------------------------------------------------------------
def test_no_photos_means_no_evidence_page(client):
    _, d = make(client)
    rd = reader(get_pdf(client, d["draft_id"]).content)
    assert image_objects(rd) == [] and "Photo evidence" not in text(rd)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_each_photo_is_embedded_once_on_a_single_evidence_page(client, n):
    _, base = make(client)
    base_pages = len(reader(get_pdf(client, base["draft_id"]).content).pages)
    _, d = make(client, photos=n)
    rd = reader(get_pdf(client, d["draft_id"]).content)
    assert len(image_objects(rd)) == n
    assert len(rd.pages) == base_pages + 1  # up to 3 photos fit on one extra page
    t = text(rd)
    assert "Photo evidence" in t and f"Photo {n} of {n}" in t


def test_embedded_photos_are_downscaled_but_stored_originals_are_untouched(client):
    s, d = make(client, photo_blobs=[jpeg_bytes((3200, 2400))])
    [img] = image_objects(reader(get_pdf(client, d["draft_id"]).content))
    assert max(int(img["/Width"]), int(img["/Height"])) <= 1600
    stored = client.app.state.db.get_session(s.id).photo_paths[0]
    with Image.open(client.app.state.settings.uploads_dir / stored) as im:
        assert im.size == (3200, 2400)


def test_exif_orientation_is_applied_in_the_pdf(client):
    _, d = make(client, photo_blobs=[jpeg_bytes((2400, 1200), orientation=6)])  # rotate 90
    [img] = image_objects(reader(get_pdf(client, d["draft_id"]).content))
    assert int(img["/Height"]) > int(img["/Width"])


def test_preview_html_never_contains_photos(client):
    _, d = make(client, photos=2)
    assert "<img" not in d["html"] and "Photo evidence" not in d["html"]


def test_missing_corrupt_or_tampered_photo_files_do_not_break_the_pdf(client):
    s, d = make(client, photos=3)
    uploads = client.app.state.settings.uploads_dir
    names = client.app.state.db.get_session(s.id).photo_paths
    (uploads / names[0]).unlink()                          # file deleted
    (uploads / names[1]).write_bytes(b"not an image")      # corrupt
    client.app.state.db.save_session(client.app.state.db.get_session(s.id).model_copy(
        update={"photo_paths": [names[0], names[1], "../../outside.jpg"]}))  # traversal attempt
    r = get_pdf(client, d["draft_id"])
    assert r.status_code == 200
    rd = reader(r.content)
    assert image_objects(rd) == [] and text(rd).count("Photo unavailable") == 3


# -- engine unavailable ---------------------------------------------------------------------
@pytest.mark.parametrize("exc", [OSError("cannot load library pango"), ImportError("no weasyprint")])
def test_missing_engine_is_503_pdf_unavailable(client, monkeypatch, exc):
    _, d = make(client)

    def boom():
        raise exc

    monkeypatch.setattr(pdf_mod, "_load_weasyprint", boom)
    r = get_pdf(client, d["draft_id"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "PDF_UNAVAILABLE"
    assert client.get("/api/health").status_code == 200  # the rest of the API is unaffected


def test_missing_font_is_503_not_a_silent_fallback(client, monkeypatch, tmp_path):
    _, d = make(client)
    monkeypatch.setattr(pdf_mod, "FONT_PATH", tmp_path / "missing.ttf")
    r = get_pdf(client, d["draft_id"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "PDF_UNAVAILABLE"
    assert "font" in r.json()["error"]["message"].lower()


# -- security of the renderer ------------------------------------------------------------------
@pytest.fixture
def fetcher():
    _, _, _, URLFetcher = pdf_mod._load_weasyprint()
    return make_fetcher(URLFetcher)


@pytest.mark.parametrize("url", [
    "http://203.0.113.7/x.png", "https://example.com/a.css", "ftp://203.0.113.7/f",
    "file:///C:/Windows/win.ini", "file:///etc/passwd", "file://server/share/x.png",
    "file:///" + str(FONT_PATH.parent.parent.parent / ".env").replace("\\", "/"),
])
def test_fetcher_blocks_everything_except_data_uris_and_the_bundled_font(fetcher, url):
    with pytest.raises(ValueError):
        fetcher.fetch(url)


def test_fetcher_allows_data_uris_and_the_bundled_font(fetcher):
    assert fetcher.fetch("data:text/plain;base64,aGk=") is not None
    resp = fetcher.fetch(FONT_PATH.as_uri())
    assert len(resp.read() if hasattr(resp, "read") else resp.body.read()) == FONT_PATH.stat().st_size


def test_bundled_font_url_recognised_in_encoded_and_raw_forms():
    assert _is_bundled_font(FONT_PATH.as_uri())
    if sys.platform == "win32":  # the raw drive-letter form (file:///C:/...) only exists on Windows
        assert _is_bundled_font("file:///" + str(FONT_PATH).replace("\\", "/"))
    assert not _is_bundled_font(FONT_PATH.with_name("OFL.txt").as_uri())
    assert not _is_bundled_font("http://example.com/" + FONT_PATH.name)


def test_html_with_remote_and_local_references_renders_without_fetching_them(monkeypatch):
    requested: list[str] = []
    real_open = urllib.request.OpenerDirector.open

    def spy(self, fullurl, *a, **k):
        requested.append(fullurl.full_url if hasattr(fullurl, "full_url") else str(fullurl))
        return real_open(self, fullurl, *a, **k)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", spy)
    html = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<link rel='stylesheet' href='http://203.0.113.7/evil.css'></head><body>"
            "<img src='http://203.0.113.7/x.png'><img src='file:///C:/Windows/win.ini'>"
            "<p>தமிழ் text</p></body></html>")
    data = render_pdf(html)
    assert data.startswith(b"%PDF-")
    assert requested, "the bundled font should have been loaded"
    assert all(u.startswith("data:") or _is_bundled_font(u) for u in requested), requested


def test_two_simultaneous_renders_both_succeed():
    results, errors = [], []

    def work():
        try:
            results.append(render_pdf("<!doctype html><html><body><p>தமிழ் / English</p></body></html>"))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    assert not errors and len(results) == 2 and all(r.startswith(b"%PDF-") for r in results)


# -- privacy and isolation ----------------------------------------------------------------------
def test_pdf_is_built_in_memory_and_leaves_no_files(client):
    _, d = make(client, photos=2)
    root = client.app.state.settings.data_dir
    before = sorted(str(p) for p in root.rglob("*"))
    get_pdf(client, d["draft_id"])
    assert sorted(str(p) for p in root.rglob("*")) == before


def test_logs_contain_timing_but_no_personal_data(client, caplog):
    _, d = make(client, summary_en="Very private summary text.",
                complainant={"name": "Secret Person", "address": "Secret Street 9"})
    with caplog.at_level("DEBUG"):
        get_pdf(client, d["draft_id"])
    log_text = caplog.text
    assert "pdf rendered" in log_text
    for private in ("Very private summary text.", "Secret Person", "Secret Street 9"):
        assert private not in log_text


def test_pdf_metadata_holds_the_draft_id_but_not_the_complainant(client):
    _, d = make(client, complainant={"name": "Secret Person", "address": "Secret Street 9"})
    meta = reader(get_pdf(client, d["draft_id"]).content).metadata
    joined = " ".join(str(v) for v in meta.values())
    assert d["draft_id"] in joined and "Secret Person" not in joined and "Secret Street" not in joined


def test_pdf_endpoint_needs_no_model_provider(client):
    from backend.deps import get_provider_factory

    def boom():
        raise AssertionError("no model provider may be built for PDFs")

    client.app.dependency_overrides[get_provider_factory] = lambda: boom
    _, d = make(client)
    assert get_pdf(client, d["draft_id"]).status_code == 200
