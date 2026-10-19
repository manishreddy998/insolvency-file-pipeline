"""Small cases taken from misreads seen on the 300 packet run."""
from filepipe.extract import get_extractor
from filepipe.extract.base import Cite, FileExtraction, Value
from filepipe.extract.local import DOUBT_CONF, _repaired
from filepipe.extract.parse import same_person
from filepipe.verify import REVIEW_CONF, verify


def test_el_is_read_as_ei():
    ex = get_extractor("layout-v2")
    assert ex.split("El: $42.55", "pay_stub") == ("ei", "$42.55")


def test_repaired_values_go_to_review():
    assert _repaired("postal", "TOT 1G6")
    assert _repaired("postal", "MA4N 5X3")
    assert not _repaired("postal", "M4N 5X3")
    assert _repaired("balance", "§,155.33")
    assert not _repaired("net", "$1,956.79")
    assert DOUBT_CONF < REVIEW_CONF


def test_household_members_are_different_people():
    assert not same_person("Cindy Frederick", "Craig Frederick")
    assert not same_person("John Lewis", "Joseph Lewis")
    assert same_person("Christopher Davis", "Christophr Davis")


def _fx(**kw):
    fx = FileExtraction("F1", "layout-v2")
    c = Cite(1, "x", 0.95)
    fx.intake = {"name": Value("Ann Lee", c), "persons": Value(1, c), "stated_income": Value(2000.0, c),
                 "spouse_stated": Value(kw.get("spouse", 0.0), c), "signed_date": Value("2026-09-15", c)}
    fx.stubs = [{"employee": Value("Ann Lee", c), "net": Value(1000.0, c), "frequency": Value("semimonthly", c),
                 "pay_date": Value("2026-09-10", c), "employer": Value("Acme", c), "page": 2}]
    fx.tradelines = [{"creditor": Value("Bank", c), "kind": "credit card", "last4": Value("1111", c), "balance": Value(500.0, c)}]
    fx.bank = {"credit_total": Value(kw.get("total", 500.0), c)}
    return fx


def test_unread_credit_lines_are_carried_at_the_report_total():
    r = verify(_fx(total=1700.0))
    assert r.figures["unsecured_total"] == 1700.0
    assert any(f["code"] == "creditor_lines_unread" for f in r.findings)


def test_spouse_income_without_a_stub_is_flagged():
    r = verify(_fx(spouse=2500.0))
    assert any(f["code"] == "spouse_income_unproven" for f in r.findings)
    assert not any(f["code"] == "spouse_income_unproven" for f in verify(_fx()).findings)
