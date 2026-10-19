from filepipe.radar.features import HORIZON, snapshots
from filepipe.radar.model import gate, split, train_all
from filepipe.synth.ledger import simulate

RULES = {"min_auc_gain": 0.01, "recall_at_workload_may_not_drop": True}


def _small():
    return simulate(1500, 5)


def test_ledger_outcomes_are_plausible():
    files, months = _small()
    share = files["outcome"].value_counts(normalize=True)
    assert set(share.index) <= {"active", "completed", "annulled"}
    assert 0.02 < share.get("annulled", 0) < 0.25
    assert (months.groupby("file_id")["month"].is_monotonic_increasing).all()


def test_annulled_files_reach_three_payments_behind():
    files, months = _small()
    ann = files[files["outcome"] == "annulled"]["file_id"]
    worst = months[months["file_id"].isin(ann)].groupby("file_id")["arrears_payments"].max()
    assert (worst >= 3 - 1e-6).all()


def test_labels_do_not_look_past_the_horizon():
    files, months = _small()
    snap = snapshots(files, months)
    pos = snap[snap["label"] == 1]
    assert (pos["months_to_annul"] <= HORIZON).all()
    assert (pos["months_to_annul"] >= 1).all()


def test_split_is_by_file_and_negative_control_is_blocked():
    files, months = _small()
    res = train_all(files, months)
    train, test = split(res["snap"])
    assert not set(train["file_id"]) & set(test["file_id"])
    rep = res["report"]
    assert rep["radar-intake-only"]["auc"] < rep["radar-logit-v1"]["auc"]
    assert gate(rep, "radar-logit-v1", "radar-intake-only", RULES)["decision"] == "block"


def test_gate_promotes_only_clear_wins():
    rep = {"a": {"auc": 0.90, "recall_at_workload": 0.80}, "b": {"auc": 0.905, "recall_at_workload": 0.85},
           "c": {"auc": 0.95, "recall_at_workload": 0.79}, "d": {"auc": 0.93, "recall_at_workload": 0.82}}
    assert gate(rep, "a", "b", RULES)["decision"] == "block"
    assert gate(rep, "a", "c", RULES)["decision"] == "block"
    assert gate(rep, "a", "d", RULES)["decision"] == "promote"
