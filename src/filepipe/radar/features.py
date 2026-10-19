"""Month end snapshots of every active proposal, with what was known that day and what happened next."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 3  # months: will the proposal be deemed annulled within the next three months?

BEHAVIOUR = ["arrears_payments", "missed_last3", "missed_last6", "partial_last3", "nsf_last3", "late_days_last3",
             "late_trend", "contact_last3", "ever_missed", "months_since_last_miss"]
INTAKE = ["payment_to_income", "intake_flags", "prior_insolvency", "pad", "support_obligation", "persons",
          "income_salaried", "income_hourly", "income_self_employed", "income_gig"]
CLOCK = ["months_on_book", "months_left"]
ALL = BEHAVIOUR + INTAKE + CLOCK


def snapshots(files: pd.DataFrame, months: pd.DataFrame) -> pd.DataFrame:
    m = months.sort_values(["file_id", "m"]).copy()
    g = m.groupby("file_id")
    for col, w, name in [("missed", 3, "missed_last3"), ("missed", 6, "missed_last6"), ("partial", 3, "partial_last3"),
                         ("nsf", 3, "nsf_last3"), ("contact", 3, "contact_last3"), ("days_late", 3, "late_days_last3")]:
        m[name] = g[col].transform(lambda s: s.rolling(w, min_periods=1).sum())
    m["late_trend"] = g["days_late"].transform(lambda s: s.rolling(3, min_periods=1).mean() - s.rolling(6, min_periods=1).mean())
    m["ever_missed"] = g["missed"].cummax()
    last_miss = m["m"].where(m["missed"] == 1)
    m["months_since_last_miss"] = (m["m"] - last_miss.groupby(m["file_id"]).ffill()).fillna(99)
    f = files.set_index("file_id")
    m = m.join(f[["payment_to_income", "intake_flags", "prior_insolvency", "pad", "support_obligation", "persons",
                  "income_type", "term", "outcome", "end_month"]], on="file_id")
    for t in ["salaried", "hourly", "self_employed", "gig"]:
        m[f"income_{t}"] = (m["income_type"] == t).astype(int)
    m["months_on_book"] = m["m"]
    m["months_left"] = m["term"] - m["m"]
    # label: annulled in the next HORIZON months (the annulment month itself is not a snapshot to score)
    end = pd.to_datetime(m["end_month"])
    now = pd.to_datetime(m["month"])
    ahead = (end.dt.year - now.dt.year) * 12 + (end.dt.month - now.dt.month)
    m["label"] = ((m["outcome"] == "annulled") & (ahead >= 1) & (ahead <= HORIZON)).astype(int)
    m["months_to_annul"] = np.where(m["outcome"] == "annulled", ahead, np.nan)
    terminal = (m["outcome"] != "active") & (ahead <= 0)
    return m[~terminal].reset_index(drop=True)
