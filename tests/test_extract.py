"""End to end on a few digital packets: render, read the text layer, extract, verify."""
import json

import pytest

from filepipe import config
from filepipe.evaluate import evaluate
from filepipe.extract import get_extractor
from filepipe.ocr import read_packet
from filepipe.synth.build import build_batch
from filepipe.verify import verify


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    out = tmp_path_factory.mktemp("packets")
    import filepipe.synth.build as b
    b.CAPTURE_MIX = {"digital": 1.0}
    m = build_batch(n=16, seed=21, out_dir=out, workers=2, trap_rate=0.9)
    rows = [json.loads(l) for l in m.read_text().splitlines()]
    return out, rows


def test_digital_packets_read_exactly(batch):
    out, rows = batch
    ex = get_extractor("layout-v2")
    triples = []
    for m in rows:
        fx = ex.extract(m["file_id"], read_packet(out / m["path"]))
        triples.append((m, fx, verify(fx)))
    r = evaluate(triples)
    assert r["field_accuracy"] == 1.0
    assert r["surplus_payment_exact"] == 1.0
    assert r["trap_recall"] == 1.0 and r["trap_false_alarms"] == 0
    assert r["files_wrong_and_not_flagged"] == 0


def test_every_number_in_the_prefill_has_a_source(batch):
    out, rows = batch
    ex = get_extractor("layout-v2")
    fx = ex.extract(rows[0]["file_id"], read_packet(out / rows[0]["path"]))
    res = verify(fx)
    assert res.prefill and all(r["source"] for r in res.prefill)
    for c in res.creditors:
        assert c["page"] >= 1


def test_simple_reader_is_registered():
    assert get_extractor("labels-v1").name == "labels-v1"
    assert get_extractor("layout-v2-fastocr").ocr == "fast"
