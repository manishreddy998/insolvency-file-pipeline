"""The Azure extractor without Azure: a fake client returns word boxes taken from a digital packet."""
import json

import pymupdf
import pytest

import filepipe.azure_di as az
from filepipe.evaluate import evaluate
from filepipe.extract import get_extractor
from filepipe.verify import verify


class FakeResult(dict):
    def as_dict(self):
        return dict(self)


class FakePoller:
    def __init__(self, r):
        self.r = r

    def result(self):
        return self.r


class FakeClient:
    """Builds an Azure style result (pages, words, polygons in inches, confidence) from the PDF text layer."""
    def __init__(self):
        self.calls = 0

    def begin_analyze_document(self, model_id, body, content_type=None):
        self.calls += 1
        self.max_pages = max(getattr(self, "max_pages", 0), len(pymupdf.open(stream=body.getvalue(), filetype="pdf")))
        doc = pymupdf.open(stream=body.getvalue(), filetype="pdf")
        pages = []
        for i, pg in enumerate(doc):
            words = []
            for x0, y0, x1, y1, w, *_ in pg.get_text("words"):
                k = 1 / 72
                words.append({"content": w, "confidence": 0.98,
                              "polygon": [x0 * k, y0 * k, x1 * k, y0 * k, x1 * k, y1 * k, x0 * k, y1 * k]})
            pages.append({"pageNumber": i + 1, "angle": 0.0, "unit": "inch", "words": words})
        return FakePoller(FakeResult({"pages": pages}))


@pytest.fixture()
def packets(tmp_path, monkeypatch):
    import filepipe.synth.build as b
    monkeypatch.setattr(b, "CAPTURE_MIX", {"digital": 1.0})
    m = b.build_batch(n=3, seed=31, out_dir=tmp_path / "p", workers=1, trap_rate=0.9)
    monkeypatch.setattr(az, "CACHE", tmp_path / "azure")
    return tmp_path / "p", [json.loads(l) for l in m.read_text().splitlines()]


def test_skipped_cleanly_without_settings(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_DI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DI_KEY", raising=False)
    monkeypatch.setattr(az, "RESULTS", tmp_path)
    monkeypatch.setattr(az, "CACHE", tmp_path / "azure")
    assert not az.configured()
    assert "skipped" in az.side_by_side(use_mlflow=False)


def test_fake_client_reads_like_the_text_layer(packets):
    out, rows = packets
    client = FakeClient()
    ex = get_extractor("azure-di-layout")
    triples = []
    for r in rows:
        res = az.analyze(out / r["path"], r["file_id"], len(r["pages"]), client=client)
        fx = ex.extract(r["file_id"], az.to_packet(res))
        triples.append((r, fx, verify(fx)))
    rep = evaluate(triples)
    assert rep["field_accuracy"] == 1.0 and rep["trap_recall"] == 1.0
    assert rep["files_wrong_and_not_flagged"] == 0


def test_cache_means_one_call_per_file(packets):
    out, rows = packets
    client = FakeClient()
    r = rows[0]
    az.analyze(out / r["path"], r["file_id"], len(r["pages"]), client=client)
    az.analyze(out / r["path"], r["file_id"], len(r["pages"]), client=client)
    assert client.calls == len(r["pages"])  # one call per page, cached afterwards
    assert client.max_pages == 1  # F0 only analyses two pages per call, so we send one
    assert az.pages_used_this_month() == len(r["pages"])


def test_page_caps_stop_before_sending(packets, monkeypatch):
    out, rows = packets
    client = FakeClient()
    monkeypatch.setattr(az, "RUN_PAGE_CAP", 2)
    with pytest.raises(az.BudgetExceeded):
        az.analyze(out / rows[0]["path"], rows[0]["file_id"], 5, client=client, run_pages=[])
    assert client.calls == 0


def test_rotated_page_rows_are_rebuilt():
    # a page turned 90 degrees: Azure reports the angle and words in page coordinates
    def word(t, x, y):
        return {"content": t, "confidence": 0.9, "polygon": [x, y, x + 0.1, y, x + 0.1, y + 0.5, x, y + 0.5]}
    import math
    words = []
    for t, (x, y) in (("Net", (1.0, 1.0)), ("Pay:", (1.6, 1.0)), ("$100.00", (2.4, 1.0))):
        a = math.radians(90)
        rx, ry = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        words.append(word(t, rx, ry))
    pt = az.to_packet({"pages": [{"pageNumber": 1, "angle": 90.0, "words": words}]})
    assert [l.text for l in pt.lines] == ["Net Pay: $100.00"]


def test_subset_stays_under_the_page_cap():
    rows = [{"file_id": f"F{i}", "capture": c, "pages": [{}] * 6} for i, c in enumerate(["scan", "fax", "phone", "digital"] * 20)]
    s = az.subset(rows, page_cap=150)
    assert sum(len(r["pages"]) for r in s) <= 150
    assert all(r["capture"] != "digital" for r in s)
