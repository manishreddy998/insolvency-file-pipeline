"""Load pipeline outputs into Postgres (schema raw). dbt builds staging and marts on top."""
from __future__ import annotations

import io
import json

import pandas as pd
from sqlalchemy import create_engine, text

from filepipe.config import CONFIGS, WORK, database_url

CSV_TABLES = {
    "proposals": "proposals.csv", "proposal_payments": "proposal_payments.csv", "radar_scores": "radar_scores.csv",
    "lead_touches": "lead_touches.csv", "funnel_people": "funnel_people.csv", "channel_cost": "channel_cost.csv",
    "osb_fsa_monthly": "osb_fsa_monthly.csv", "osb_fsa_forecast": "osb_fsa_forecast.csv",
}


def packet_tables(extractor: str = "layout-v2") -> dict[str, pd.DataFrame]:
    files, findings, prefill = [], [], []
    path = WORK / f"extract.{extractor}.jsonl"
    for line in path.read_text().splitlines():
        r = json.loads(line)["result"]
        s = r.get("surplus") or {}
        f = r["figures"]
        files.append({"file_id": r["file_id"], "extractor": r["extractor"],
                      **{k: f.get(k) for k in ("debtor_monthly", "main_job_monthly", "side_income", "spouse_monthly",
                                               "child_support", "persons", "unsecured_total", "frequency", "stated_income")},
                      "fsa": (f.get("postal") or "")[:3] or None,
                      **{k: v for k, v in s.items() if k != "steps"},
                      "n_fields": r["n_fields"], "n_review_fields": len(r["review_fields"]),
                      "n_checks": sum(x["severity"] == "check" for x in r["findings"])})
        for x in r["findings"]:
            findings.append({"file_id": r["file_id"], "code": x["code"], "severity": x["severity"],
                             "message": x["message"], "pages": ",".join(str(p) for p in x["pages"] if p)})
        prefill += r["prefill"]
    return {"packet_files": pd.DataFrame(files), "packet_findings": pd.DataFrame(findings),
            "prefill_rows": pd.DataFrame(prefill)}


def load(url: str | None = None, extractor: str = "layout-v2") -> dict:
    url = url or database_url()
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    eng = create_engine(url)
    with eng.begin() as con:
        con.execute(text("create schema if not exists raw"))
    counts = {}
    frames = {name: pd.read_csv(WORK / fn) for name, fn in CSV_TABLES.items() if (WORK / fn).exists()}
    frames["office_fsas"] = pd.read_csv(CONFIGS / "farber_office_fsas.csv")
    if (WORK / f"extract.{extractor}.jsonl").exists():
        frames.update(packet_tables(extractor))
    for name, df in frames.items():
        df.head(0).to_sql(name, eng, schema="raw", if_exists="replace", index=False)
        buf = io.StringIO()
        df.to_csv(buf, index=False, header=False)
        buf.seek(0)
        raw = eng.raw_connection()
        try:
            with raw.cursor() as cur, cur.copy(f'COPY raw."{name}" FROM STDIN WITH (FORMAT csv)') as cp:
                cp.write(buf.getvalue())
            raw.commit()
        finally:
            raw.close()
        counts[name] = int(len(df))
    return counts


if __name__ == "__main__":
    print(load())
