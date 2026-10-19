from fastapi.testclient import TestClient

from filepipe.api import app


def test_health_and_missing_file():
    c = TestClient(app)
    assert c.get("/health").json()["ok"] is True
    assert c.get("/files/NOPE").status_code == 404


def test_rejects_non_pdf():
    c = TestClient(app)
    r = c.post("/packets", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_digital_packet_round_trip(tmp_path, monkeypatch):
    import filepipe.api as api
    import filepipe.synth.build as b
    monkeypatch.setattr(api, "UPLOADS", tmp_path / "up")
    b.CAPTURE_MIX = {"digital": 1.0}
    m = b.build_batch(n=1, seed=5, out_dir=tmp_path, workers=1)
    pdf = next(tmp_path.glob("*.pdf"))
    r = TestClient(app).post("/packets", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["surplus"]["line15_monthly_payment"] is not None
    assert body["note"] and body["note_writer"] in ("template", "local-model")
    assert TestClient(app).get(f"/files/{body['file_id']}").status_code == 200
