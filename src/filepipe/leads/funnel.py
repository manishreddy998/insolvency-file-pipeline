"""Lead to completed: count people, not touches, and credit channels with files that finish."""
from __future__ import annotations

import json

import pandas as pd

from filepipe.config import RESULTS, WORK
from filepipe.leads.resolve import baseline, pair_scores, resolve
from filepipe.leads.synth import CHANNELS, COST_PER_TOUCH, simulate_leads


def channel_table(people: pd.DataFrame, touches: pd.DataFrame, cluster: pd.Series) -> pd.DataFrame:
    t = touches.assign(cluster=cluster.values).sort_values("ts")
    first = t.groupby("cluster").first()
    last = t.groupby("cluster").last()
    # the person behind a cluster is the one with most touches in it (the join an intake team makes at signing)
    who = t.groupby("cluster")["person_id"].agg(lambda s: s.value_counts().index[0])
    p = people.set_index("person_id").loc[who.values].reset_index()
    p["cluster"] = who.index
    p["first_touch"] = first.loc[p["cluster"], "channel"].values
    p["last_touch"] = last.loc[p["cluster"], "channel"].values
    p["first_ts"] = first.loc[p["cluster"], "ts"].values
    p["touches"] = t.groupby("cluster").size().loc[p["cluster"]].values
    p[["cluster", "first_touch", "last_touch", "first_ts", "touches", "consult", "signed", "filed", "file_id"]].to_csv(
        WORK / "funnel_people.csv", index=False)
    rows = []
    for ch in CHANNELS:
        raw = int((t["channel"] == ch).sum())
        cost = raw * COST_PER_TOUCH[ch]
        g = p[p["first_touch"] == ch]
        filed = int(g["filed"].sum())
        completed = int((g["outcome"] == "completed").sum())
        annulled = int((g["outcome"] == "annulled").sum())
        rows.append({"channel": ch, "touches": raw, "spend": round(cost, 0), "people_first_touch": int(len(g)),
                     "consults": int(g["consult"].sum()), "filed": filed, "completed": completed, "annulled": annulled,
                     "filed_last_touch_credit": int(p[(p["last_touch"] == ch)]["filed"].sum()),
                     "cost_per_touch": round(cost / max(raw, 1), 2),
                     "cost_per_person": round(cost / max(len(g), 1), 2),
                     "cost_per_filed": round(cost / max(filed, 1), 2),
                     "cost_per_completed": round(cost / max(completed, 1), 2) if completed else None,
                     "annulled_share_of_closed": round(annulled / max(annulled + completed, 1), 4)})
    return pd.DataFrame(rows)


def run(n_files: int = 5000, seed: int = 11) -> dict:
    from filepipe.synth.ledger import simulate
    files, _ = simulate(n_files, seed)
    people, touches = simulate_leads(files)
    truth = touches["person_id"]
    base = baseline(touches)
    res = resolve(touches)
    WORK.mkdir(parents=True, exist_ok=True)
    people.to_csv(WORK / "lead_people_truth.csv", index=False)
    touches.assign(cluster_baseline=base.values, cluster=res.values).to_csv(WORK / "lead_touches.csv", index=False)
    table = channel_table(people, touches, res)
    table.to_csv(WORK / "funnel_by_channel.csv", index=False)
    pd.DataFrame([{"channel": c, "cost_per_touch": v} for c, v in COST_PER_TOUCH.items()]).to_csv(
        WORK / "channel_cost.csv", index=False)
    shared = people["household_of"].notna().sum()
    out = {"people": int(len(people)), "touches": int(len(touches)), "filed_people": int(people["filed"].sum()),
           "people_sharing_a_household_phone": int(shared),
           "identity_baseline_exact_email_or_phone": pair_scores(truth, base),
           "identity_resolver": pair_scores(truth, res),
           "raw_touches_per_true_person": round(len(touches) / len(people), 3),
           "by_channel": table.to_dict(orient="records"),
           "spend_note": "Spend is synthetic: touches x a made up cost per touch per channel."}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "funnel.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "by_channel"}, indent=1))
    print(pd.DataFrame(r["by_channel"]).to_string())
