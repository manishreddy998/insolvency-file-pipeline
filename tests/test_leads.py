import pandas as pd

from filepipe.leads.resolve import baseline, norm_email, norm_phone, pair_scores, resolve
from filepipe.leads.synth import simulate_leads
from filepipe.synth.ledger import simulate


def _t(rows):
    return pd.DataFrame([{"touch_id": f"T{i}", "person_id": r[0], "channel": "call", "ts": f"2026-01-0{i + 1}",
                          "name": r[1], "phone": r[2], "email": r[3], "fsa": r[4]} for i, r in enumerate(rows)])


def test_normalisers():
    assert norm_phone("+1 (416) 555-0101") == "4165550101"
    assert norm_phone("555-0101") == ""
    assert norm_email("Jo.Ann+farber@Gmail.com") == "joann@gmail.com"
    assert norm_email("A.B@outlook.com") == "a.b@outlook.com"


def test_shared_home_phone_is_not_one_person():
    t = _t([("A", "Priya Shah", "416-555-0101", "", "M1B"), ("B", "Ravi Shah", "(416) 555-0101", "", "M1B")])
    assert resolve(t).nunique() == 2
    assert baseline(t.assign(phone="4165550101")).nunique() == 1  # the simple rule merges them


def test_nickname_typo_and_formats_join():
    t = _t([("A", "Robert Kim", "4165550101", "", ""), ("A", "Rob Kim", "+1 416 555 0101", "", ""),
            ("A", "Robret Kim", "", "rob.kim@gmail.com", "L5B"), ("A", "Robert Kim", "555-0101", "ROB.KIM@gmail.com", "")])
    assert resolve(t).nunique() == 1


def test_pair_scores():
    truth = pd.Series(["a", "a", "b", "b"])
    pred = pd.Series([1, 1, 1, 2])
    s = pair_scores(truth, pred)
    assert s["precision"] == round(1 / 3, 4) and s["recall"] == 0.5


def test_resolver_beats_exact_rule_on_synthetic_leads():
    files, _ = simulate(400, 3)
    people, touches = simulate_leads(files, extra_people=600, seed=4)
    assert people["filed"].sum() == 400
    b = pair_scores(touches["person_id"], baseline(touches))
    r = pair_scores(touches["person_id"], resolve(touches))
    assert r["recall"] > b["recall"] + 0.3
    assert r["precision"] >= 0.95
