"""File to Finish dashboard. Every person, file and lead here is synthetic. FSA counts are real OSB data."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
RESULTS = ROOT / "results"
DB = os.environ.get("DATABASE_URL", "")

st.set_page_config(page_title="File to Finish", layout="wide")
st.markdown("<style>.block-container{padding-top:1.5rem} h1{font-weight:600}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def sql(q: str) -> pd.DataFrame | None:
    if not DB:
        return None
    try:
        from sqlalchemy import create_engine
        url = DB.replace("postgresql://", "postgresql+psycopg://", 1)
        return pd.read_sql(q, create_engine(url))
    except Exception:
        return None


def rj(name: str) -> dict:
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else {}


@st.cache_data(ttl=60)
def files() -> list[dict]:
    p = WORK / "extract.layout-v2.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


st.title("File to Finish")
st.caption("Intake packet to filed proposal to completed proposal. Synthetic people and files; real OSB filing counts.")
tabs = st.tabs(["Review queue", "Proposal radar", "Lead to completed", "Demand by FSA", "Your numbers", "How it scores"])

# 1. review queue
with tabs[0]:
    rows = files()
    notes = {}
    for mode in ("model", "template"):
        p = WORK / f"notes.{mode}.jsonl"
        if p.exists():
            notes = {n["file_id"]: n for n in map(json.loads, p.read_text().splitlines())}
            break
    if not rows:
        st.info("Run the pipeline first.")
    else:
        q = []
        for r in rows:
            res = r["result"]
            checks = [f["code"] for f in res["findings"] if f["severity"] == "check"]
            q.append({"file_id": res["file_id"], "status": "needs review" if checks or res["review_fields"] else "ready",
                      "checks": ", ".join(checks), "fields_to_review": len(res["review_fields"]),
                      "net_income": res["figures"]["debtor_monthly"], "persons": res["figures"]["persons"],
                      "surplus_payment": (res.get("surplus") or {}).get("line15_monthly_payment"),
                      "unsecured": res["figures"]["unsecured_total"]})
        qdf = pd.DataFrame(q)
        c1, c2, c3 = st.columns(3)
        c1.metric("Packets", len(qdf))
        c2.metric("Ready, no checks", int((qdf["status"] == "ready").sum()))
        c3.metric("Need a person", int((qdf["status"] != "ready").sum()))
        only = st.toggle("Only files that need review", value=True)
        view = qdf[qdf["status"] != "ready"] if only else qdf
        st.dataframe(view, hide_index=True, use_container_width=True, height=300)
        pick = st.selectbox("Open a file", view["file_id"].tolist() or qdf["file_id"].tolist())
        res = next(r["result"] for r in rows if r["result"]["file_id"] == pick)
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Checks")
            for f in res["findings"]:
                st.write(f"**{f['code'].replace('_', ' ')}**: {f['message']} (pages {', '.join(map(str, [p for p in f['pages'] if p]))})")
            if res["review_fields"]:
                st.write("Fields to confirm:", ", ".join(x["field"] for x in res["review_fields"]))
            st.subheader("Surplus income, Directive 11R2-2026")
            for s in (res.get("surplus") or {}).get("steps", []):
                st.write("- " + s)
        with right:
            st.subheader("Trustee note")
            n = notes.get(pick)
            st.markdown(n["note"].replace("$", "\\$") if n else "No note yet.")
            st.subheader("Prefill rows")
            pf = pd.DataFrame(res["prefill"])
            st.dataframe(pf, hide_index=True, use_container_width=True, height=240)
            ok = st.checkbox("I checked the figures above", key=f"ok-{pick}")
            st.download_button("Export prefill CSV", pf.to_csv(index=False).encode(), f"{pick}_prefill.csv",
                               disabled=not ok)

# 2. radar
with tabs[1]:
    rr = rj("radar_eval.json")
    p = WORK / "radar_scores.csv"
    if not rr or not p.exists():
        st.info("Run the radar step first.")
    else:
        best = rr["scored_with"]
        m = rr["report"][best]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Model in production", best)
        c2.metric("AUC", m["auc"])
        c3.metric("Recall at the overdue list size", m["recall_at_workload"], f"{m['recall_at_workload'] - m['overdue_rule_recall']:+.3f} vs overdue rule")
        c4.metric("Annulled files flagged before any arrears", f"{m['flagged_before_any_arrears_share']:.1%}")
        st.caption("Label: deemed annulled (BIA 66.31, three payments behind) within the next three months. "
                   "Synthetic payment histories; the gap over the overdue rule must be measured again on real files.")
        sc = pd.read_csv(p)
        st.dataframe(sc.head(40), hide_index=True, use_container_width=True)

# 3. funnel
with tabs[2]:
    fdf = sql("select * from marts.fct_funnel order by channel")
    fun = rj("funnel.json")
    if fdf is None and fun:
        fdf = pd.DataFrame(fun["by_channel"])
    if fdf is None or fdf.empty:
        st.info("Run the leads step first.")
    else:
        if fun:
            a, b = fun["identity_baseline_exact_email_or_phone"], fun["identity_resolver"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Touches", fun["touches"])
            c2.metric("People found", b["people_found"], f"{b['people_found'] - b['people_true']:+d} vs answer key")
            c3.metric("Duplicate pairs found", f"{b['recall']:.1%}", f"{b['recall'] - a['recall']:+.1%} vs exact match rule")
        st.dataframe(fdf, hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(fdf, x="channel", y=["cost_per_filed", "cost_per_completed"], barmode="group",
                               title="Cost per filed and per completed proposal (synthetic spend)"), use_container_width=True)

# 4. demand
with tabs[3]:
    dem = rj("demand.json")
    if not dem:
        st.info("Run the demand step first.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Consumer insolvencies outside Quebec, {dem['ytd_months']}", f"{dem['ytd_consumer_insolvencies_ex_quebec']:,}")
        c2.metric("Share in an FSA with a Farber office", f"{dem['ytd_share_in_office_fsas']:.1%}")
        c3.metric("Forecast error, Ontario, 6 months held out (MAPE)", f"{dem['backtest']['ontario'][dem['chosen_forecaster']]['mape']:.1%}")
        st.subheader("Busiest FSAs without an office, this year")
        st.dataframe(pd.DataFrame(dem["top_fsas_without_office"]), hide_index=True, use_container_width=True)
        fc = pd.DataFrame([{"month": k, "forecast": v} for k, v in dem["forecast_canada_ex_quebec"].items()])
        st.plotly_chart(px.bar(fc, x="month", y="forecast", title="Next six months, consumer insolvencies outside Quebec"),
                        use_container_width=True)
        st.caption("Source: OSB monthly insolvency statistics by FSA, Open Government Licence Canada. "
                   "Office FSAs from farber.ca/locations.")

# 5. ROI with Farber's own inputs
with tabs[4]:
    ex = rj("extraction_eval.json").get("layout-v2", {})
    st.write("Enter your own numbers. The two measured rates come from the 300 packet test run.")
    c1, c2 = st.columns(2)
    with c1:
        files_m = st.number_input("New files a month", 0, 100000, 0)
        mins = st.number_input("Minutes of data entry and checking per file today", 0, 600, 0)
        rate = st.number_input("Loaded staff cost per hour ($)", 0, 500, 0)
        review_mins = st.number_input("Minutes to confirm one flagged field", 0, 60, 2)
    with c2:
        active = st.number_input("Proposals under administration", 0, 1000000, 0)
        ann = st.number_input("Share annulled each year (%)", 0.0, 100.0, 0.0)
        saved = st.number_input("Share of those you could save with an earlier call (%)", 0.0, 100.0, 0.0)
        value = st.number_input("Average remaining trustee fee and creditor dividend per saved file ($)", 0, 100000, 0)
    fields_per_file = ex.get("fields_scored", 0) / max(ex.get("files", 1), 1)
    review_share = ex.get("review_share", 0.0)
    hours_now = files_m * mins / 60
    hours_new = files_m * fields_per_file * review_share * review_mins / 60
    st.metric("Staff hours a month on intake entry, today vs with review only", f"{hours_now:,.0f} vs {hours_new:,.0f}")
    st.metric("Monthly staff cost difference", f"${(hours_now - hours_new) * rate:,.0f}")
    st.metric("Value of proposals saved a year", f"${active * ann / 100 * saved / 100 * value:,.0f}")
    st.caption(f"Measured: {fields_per_file:.0f} fields per packet, {review_share:.1%} of fields sent to a person. "
               "Everything else is your input.")

# 6. scores
with tabs[5]:
    st.json(rj("summary.json"))
