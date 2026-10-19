from types import SimpleNamespace

from filepipe.claims import check_note
from filepipe.narrate import HostileWriter, facts_for, note_for, template_note

RES = SimpleNamespace(
    figures={"persons": 2, "debtor_monthly": 3300.0, "unsecured_total": 41250.5},
    surplus={"line8_family_available": 4300.0, "standard": 3381.0, "line15_monthly_payment": 352.62},
    creditors=[{}, {}, {}], findings=[{"code": "stale_stub", "severity": "check"}])


def test_supported_numbers_survive():
    f = facts_for(RES)
    out = check_note("Surplus income payment is $352.62 a month. Unsecured debt is $41,250.50.", f)
    assert len(out["kept"]) == 2 and not out["dropped"]


def test_hostile_writer_is_fully_blocked():
    n = note_for(RES, HostileWriter())
    bad = {c["raw"] for d in n["dropped"] for c in d["unsupported"]}
    assert "$12,345.67" in bad and "37%" in bad and "probably" in bad
    assert "$12,345.67" not in n["note"] and "37%" not in n["note"] and "hid" not in n["note"]
    assert "$41,250.50" in n["note"]


def test_template_note_passes_its_own_check():
    f = facts_for(RES)
    out = check_note(template_note(f), f)
    assert not out["dropped"]
