import random

import pymupdf

from filepipe.synth.households import TRAPS, make_cohort
from filepipe.synth.render import FOOTER, build_pages, draw_pdf


def test_cohort_is_deterministic_and_has_every_trap():
    a, b = make_cohort(120, seed=3), make_cohort(120, seed=3)
    assert [h.answer_key() for h in a] == [h.answer_key() for h in b]
    seen = {t for h in a for t in h.traps}
    assert seen == set(TRAPS)


def test_answer_key_matches_the_documents():
    for h in make_cohort(60, seed=5):
        k = h.answer_key()
        if "family_size_mismatch" not in h.traps:
            assert h.stated_persons == h.persons
        if "intake_understated" in h.traps:
            assert h.stated_income < k["debtor_monthly"] * 0.9
        assert k["unsecured_total"] == round(sum(d["balance"] for d in k["debts"]), 2)


def test_every_page_is_marked_synthetic(tmp_path):
    h = make_cohort(1, seed=11)[0]
    pages = build_pages(h, random.Random(1))
    out = tmp_path / "p.pdf"
    draw_pdf(pages, out)
    doc = pymupdf.open(out)
    assert len(doc) == len(pages)
    assert all(FOOTER in pg.get_text() for pg in doc)
    assert pages[0].kind == "intake"
