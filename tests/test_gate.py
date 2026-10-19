from filepipe.gate import decide, load_rules

BASE = dict(field_accuracy=0.98, auto_accepted_error_rate=0.0, trap_recall=0.95, surplus_payment_exact=0.97,
            files_wrong_and_not_flagged=0, seconds_median=8.0)


def test_better_candidate_is_promoted():
    rules = load_rules()["extraction"]["rules"]
    assert decide(BASE, dict(BASE, field_accuracy=0.99), rules)["decision"] == "promote"


def test_cheaper_but_worse_candidate_is_blocked():
    rules = load_rules()["extraction"]["rules"]
    worse = dict(BASE, field_accuracy=0.95, trap_recall=0.9, seconds_median=2.0)
    d = decide(BASE, worse, rules)
    assert d["decision"] == "block" and len(d["reasons"]) == 2


def test_one_silent_wrong_file_blocks():
    rules = load_rules()["extraction"]["rules"]
    assert decide(BASE, dict(BASE, files_wrong_and_not_flagged=1), rules)["decision"] == "block"
