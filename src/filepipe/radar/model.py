"""Proposal Survival Radar: rank active proposals by the chance of deemed annulment in the next three months.

Compared against the reminder a trustee system already sends (payment overdue), at the same call list size.
Every version is logged to MLflow; the candidate replaces production only if it passes the gate in
configs/release.yaml. A model that sees only intake facts is the negative control and must be blocked.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from filepipe.config import RESULTS
from filepipe.radar.features import ALL, BEHAVIOUR, INTAKE, snapshots

VERSIONS = {
    "radar-logit-v1": (["arrears_payments", "missed_last3", "missed_last6"], "logit"),
    "radar-gbm-v2": (ALL, "gbm"),
    "radar-intake-only": (INTAKE + ["months_on_book", "months_left"], "gbm"),
}

REASONS = [  # plain flags shown next to a score; they explain the list, they are not model internals
    ("nsf_last3", lambda r: r["nsf_last3"] > 0, "pre-authorized debit returned in the last 3 months"),
    ("partial_last3", lambda r: r["partial_last3"] > 0, "partial payment in the last 3 months"),
    ("late_trend", lambda r: r["late_trend"] > 2, "payments arriving later each month"),
    ("contact_last3", lambda r: r["contact_last3"] > 0, "client asked to change payments recently"),
    ("arrears_payments", lambda r: r["arrears_payments"] >= 1, "behind by at least one payment"),
    ("payment_to_income", lambda r: r["payment_to_income"] > 0.13, "payment is a high share of income"),
    ("intake_flags", lambda r: r["intake_flags"] > 0, "intake proof checks raised an issue"),
]


def _fit(kind: str, X, y):
    if kind == "logit":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, class_weight="balanced")).fit(X, y)
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                          l2_regularization=1.0, random_state=0).fit(X, y)


def split(snap: pd.DataFrame, test_share: float = 0.3, seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = np.array(sorted(snap["file_id"].unique()))
    rng = np.random.default_rng(seed)
    test_ids = set(rng.choice(ids, int(len(ids) * test_share), replace=False))
    is_test = snap["file_id"].isin(test_ids)
    return snap[~is_test], snap[is_test]


def workload_metrics(test: pd.DataFrame, score: np.ndarray) -> dict:
    """Each month, call as many files as the overdue reminder would flag that month, best scores first."""
    t = test.assign(score=score, overdue=(test["arrears_payments"] >= 1 - 1e-9).astype(int))
    caught_model = caught_rule = positives = calls = 0
    top20 = 0
    for _, g in t.groupby("month"):
        k = int(g["overdue"].sum())
        positives += int(g["label"].sum())
        calls += k
        if k:
            caught_model += int(g.nlargest(k, "score")["label"].sum())
            caught_rule += int(g[g["overdue"] == 1]["label"].sum())
        k20 = max(1, int(math.ceil(len(g) * 0.2)))
        top20 += int(g.nlargest(k20, "score")["label"].sum())
    return {"positives": positives, "calls_per_month_avg": round(calls / t["month"].nunique(), 1),
            "recall_at_workload": round(caught_model / max(positives, 1), 4),
            "overdue_rule_recall": round(caught_rule / max(positives, 1), 4),
            "precision_at_workload": round(caught_model / max(calls, 1), 4),
            "overdue_rule_precision": round(caught_rule / max(calls, 1), 4),
            "recall_at_top20pct": round(top20 / max(positives, 1), 4)}


def capacity_metrics(test: pd.DataFrame, score: np.ndarray, share: float) -> dict:
    """A fixed call list: the top share of active files each month. The overdue rule ranks by how far
    behind the file is (ties broken by recent misses); the model ranks by its score."""
    rule = test["arrears_payments"] + 0.01 * test["missed_last3"]
    t = test.assign(score=score, rule=rule)
    cm = cr = pos = calls = 0
    for _, g in t.groupby("month"):
        k = max(1, int(math.ceil(len(g) * share)))
        pos += int(g["label"].sum())
        calls += k
        cm += int(g.nlargest(k, "score")["label"].sum())
        cr += int(g.nlargest(k, "rule")["label"].sum())
    pct = int(round(share * 100))
    return {f"recall_at_{pct}pct": round(cm / max(pos, 1), 4), f"overdue_rule_recall_at_{pct}pct": round(cr / max(pos, 1), 4),
            f"precision_at_{pct}pct": round(cm / max(calls, 1), 4), f"overdue_rule_precision_at_{pct}pct": round(cr / max(calls, 1), 4)}


def early_warning(test: pd.DataFrame, score: np.ndarray) -> dict:
    """For proposals that were annulled: were they on the call list before the first missed payment of the
    run that ended them? The overdue reminder can never do this, by definition."""
    t = test.assign(score=score, overdue=(test["arrears_payments"] >= 1 - 1e-9).astype(int))
    on_list = []
    for _, g in t.groupby("month"):
        k = int(g["overdue"].sum())
        if k:
            on_list.append(g.nlargest(k, "score").index)
    flagged = set(np.concatenate(on_list)) if on_list else set()
    t["flagged"] = t.index.isin(flagged)
    ann = t[t["outcome"] == "annulled"].sort_values(["file_id", "m"])
    early = total = 0
    lead_model, lead_rule = [], []
    for fid, g in ann.groupby("file_id"):
        g = g[g["months_to_annul"] >= 1]
        if g.empty:
            continue
        total += 1
        # snapshots with no arrears yet, inside the 3 month horizon
        clean = g[(g["arrears_payments"] < 1 - 1e-9) & (g["months_to_annul"] <= 3)]
        early += bool(clean["flagged"].any())
        fm = g[g["flagged"]]["months_to_annul"]
        fr = g[g["overdue"] == 1]["months_to_annul"]
        lead_model.append(float(fm[fm <= 3].max()) if (fm <= 3).any() else 0.0)
        lead_rule.append(float(fr[fr <= 3].max()) if (fr <= 3).any() else 0.0)
    return {"annulled_files": total, "flagged_before_any_arrears": early,
            "flagged_before_any_arrears_share": round(early / max(total, 1), 4),
            "median_months_warning_model": float(np.median(lead_model)) if lead_model else 0.0,
            "median_months_warning_overdue_rule": float(np.median(lead_rule)) if lead_rule else 0.0}


def train_all(files: pd.DataFrame, months: pd.DataFrame) -> dict:
    snap = snapshots(files, months)
    train, test = split(snap)
    out, models = {}, {}
    rule_auc = roc_auc_score(test["label"], test["arrears_payments"])
    for name, (cols, kind) in VERSIONS.items():
        mdl = _fit(kind, train[cols].values, train["label"].values)
        p = mdl.predict_proba(test[cols].values)[:, 1]
        out[name] = {"auc": round(roc_auc_score(test["label"], p), 4), **workload_metrics(test, p),
                     **capacity_metrics(test, p, 0.01), **capacity_metrics(test, p, 0.02),
                     **early_warning(test, p), "features": cols}
        models[name] = mdl
    out["_data"] = {"proposals": int(files.shape[0]), "snapshots": int(snap.shape[0]),
                    "train_snapshots": int(train.shape[0]), "test_snapshots": int(test.shape[0]),
                    "test_positive_rate": round(float(test["label"].mean()), 4),
                    "overdue_rule_auc": round(rule_auc, 4),
                    "outcomes": files["outcome"].value_counts().to_dict()}
    return {"report": out, "models": models, "snap": snap, "test": test}


def gate(report: dict, prod: str, cand: str, rules: dict) -> dict:
    p, c = report[prod], report[cand]
    reasons = []
    if c["auc"] < p["auc"] + rules["min_auc_gain"]:
        reasons.append(f"AUC {c['auc']} is not {rules['min_auc_gain']} above {p['auc']}")
    if rules["recall_at_workload_may_not_drop"] and c["recall_at_workload"] < p["recall_at_workload"]:
        reasons.append(f"recall at workload {c['recall_at_workload']} vs {p['recall_at_workload']}")
    return {"production": prod, "candidate": cand, "decision": "block" if reasons else "promote", "reasons": reasons}


def score_current(models: dict, snap: pd.DataFrame, name: str) -> pd.DataFrame:
    """Latest month for proposals still active: score, reasons and the date the clock would run out."""
    last = snap[snap["outcome"] == "active"].sort_values("m").groupby("file_id").tail(1).copy()
    last = last[last["month"] == last["month"].max()]
    cols = VERSIONS[name][0]
    last["risk"] = models[name].predict_proba(last[cols].values)[:, 1]
    last["reasons"] = last.apply(lambda r: "; ".join(t for _, f, t in REASONS if f(r)), axis=1)
    left = (3 - last["arrears_payments"]).clip(lower=0)
    last["payments_before_annulment"] = left.round(2)
    month = pd.to_datetime(last["month"])
    last["annulment_if_no_payment"] = [ (m + pd.DateOffset(months=int(math.ceil(x)))).date().isoformat() if x > 0 else m.date().isoformat()
                                        for m, x in zip(month, left)]
    return last.sort_values("risk", ascending=False)[["file_id", "month", "risk", "arrears_payments",
                                                      "payments_before_annulment", "annulment_if_no_payment", "reasons"]]


def log_and_register(res: dict, decisions: list[dict]) -> dict:
    """MLflow runs for every version, registered under one name; the alias production follows the gate."""
    import mlflow
    import mlflow.sklearn
    from mlflow import MlflowClient

    from filepipe.config import mlflow_uri
    mlflow.set_tracking_uri(mlflow_uri())
    mlflow.set_experiment("survival-radar")
    client = MlflowClient()
    versions = {}
    for name, m in res["report"].items():
        if name.startswith("_"):
            continue
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params({"version": name, "n_features": len(m["features"])})
            mlflow.log_metrics({k: float(v) for k, v in m.items() if isinstance(v, (int, float))})
            info = mlflow.sklearn.log_model(res["models"][name], name="model", registered_model_name="survival-radar")
            mv = client.search_model_versions(f"run_id='{run.info.run_id}'")[0]
            client.set_model_version_tag("survival-radar", mv.version, "radar_version", name)
            versions[name] = mv.version
    prod = decisions[0]["production"]
    client.set_registered_model_alias("survival-radar", "production", versions[prod])
    for d in decisions:
        client.set_model_version_tag("survival-radar", versions[d["candidate"]], "gate", d["decision"])
        if d["decision"] == "promote":
            client.set_registered_model_alias("survival-radar", "production", versions[d["candidate"]])
    alias = client.get_model_version_by_alias("survival-radar", "production")
    return {"versions": versions, "production_version": alias.version,
            "production_name": client.get_model_version("survival-radar", alias.version).tags.get("radar_version")}


def run(n: int = 5000, seed: int = 11, use_mlflow: bool = True) -> dict:
    import yaml

    from filepipe.config import CONFIGS, WORK
    from filepipe.synth.ledger import simulate
    files, months = simulate(n, seed)
    WORK.mkdir(parents=True, exist_ok=True)
    files.to_csv(WORK / "proposals.csv", index=False)
    months.to_csv(WORK / "proposal_payments.csv", index=False)
    res = train_all(files, months)
    cfg = yaml.safe_load((CONFIGS / "release.yaml").read_text())["radar"]
    decisions = [gate(res["report"], cfg["production"], cfg["candidate"], cfg["rules"]),
                 gate(res["report"], cfg["production"], cfg["negative_control"], cfg["rules"])]
    reg = log_and_register(res, decisions) if use_mlflow else {}
    best = reg.get("production_name") or (cfg["candidate"] if decisions[0]["decision"] == "promote" else cfg["production"])
    current = score_current(res["models"], res["snap"], best)
    current.to_csv(WORK / "radar_scores.csv", index=False)
    out = {"report": res["report"], "gate": decisions, "registry": reg, "scored_with": best,
           "active_scored": int(current.shape[0])}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "radar_eval.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    import sys
    r = run(use_mlflow="--no-mlflow" not in sys.argv)
    print(json.dumps({k: {x: v[x] for x in ("auc", "recall_at_workload", "overdue_rule_recall", "precision_at_workload",
                                              "recall_at_2pct", "overdue_rule_recall_at_2pct",
                                              "flagged_before_any_arrears_share")}
                      for k, v in r["report"].items() if not k.startswith("_")}, indent=1))
    print(r["report"]["_data"], r["gate"], r["registry"])
