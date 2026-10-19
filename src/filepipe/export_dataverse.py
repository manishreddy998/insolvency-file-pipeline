"""Dataverse ready export: one CSV per table plus a JSON schema, ready for a Dataflow or an import job.

Table and column names use a publisher prefix (f2f_) and Dataverse style lower case logical names.
Every extracted value carries the packet page it came from, the line read, the confidence and whether
a cross check proved it, so a reviewer in a model driven app can open the page behind any number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from filepipe.config import DATA, WORK

OUT = DATA / "export" / "dataverse"
PREFIX = "f2f_"

SCHEMA = {
    "f2f_intakefile": {
        "display": "Intake file", "primary": "f2f_fileid",
        "columns": {"f2f_fileid": ("Text", "File ID"), "f2f_extractor": ("Text", "Extractor version"),
                    "f2f_status": ("Choice", "Status: ready or needs review"),
                    "f2f_persons": ("Whole number", "Persons in household (Directive 11R2 para 6)"),
                    "f2f_debtornetmonthly": ("Currency", "Debtor monthly net income"),
                    "f2f_spousenetmonthly": ("Currency", "Spouse monthly net income"),
                    "f2f_unsecuredtotal": ("Currency", "Unsecured debt total"),
                    "f2f_checks": ("Whole number", "Proof checks raised"),
                    "f2f_fieldstoreview": ("Whole number", "Fields sent to a person")}},
    "f2f_incomeexpense": {
        "display": "Income and expense (Form 65 lines)", "primary": "f2f_fileid",
        "columns": {"f2f_fileid": ("Lookup", "Intake file"),
                    "f2f_line1debtornetincome": ("Currency", "Line 1 debtor net income"),
                    "f2f_line2othermembersnetincome": ("Currency", "Line 2 other members net income"),
                    "f2f_line3familynetincome": ("Currency", "Line 3 family net income"),
                    "f2f_line6familynondiscretionary": ("Currency", "Line 6 family non discretionary expenses"),
                    "f2f_line8familyavailable": ("Currency", "Line 8 family available income"),
                    "f2f_line9debtorsharepct": ("Decimal", "Line 9 debtor share percent"),
                    "f2f_standard": ("Currency", "Superintendent standard used"),
                    "f2f_familysurplus": ("Currency", "Family surplus"),
                    "f2f_line15monthlypayment": ("Currency", "Line 15 surplus income payment"),
                    "f2f_steps": ("Multiline text", "How the number was worked out")}},
    "f2f_creditor": {
        "display": "Creditor", "primary": "f2f_creditorid",
        "columns": {"f2f_creditorid": ("Text", "Creditor row ID"), "f2f_fileid": ("Lookup", "Intake file"),
                    "f2f_name": ("Text", "Creditor"), "f2f_accountlast4": ("Text", "Account ending"),
                    "f2f_balance": ("Currency", "Balance"), "f2f_source": ("Choice", "Source document"),
                    "f2f_sourcepage": ("Whole number", "Packet page")}},
    "f2f_finding": {
        "display": "Proof check finding", "primary": "f2f_findingid",
        "columns": {"f2f_findingid": ("Text", "Finding ID"), "f2f_fileid": ("Lookup", "Intake file"),
                    "f2f_code": ("Choice", "Check"), "f2f_severity": ("Choice", "check or info"),
                    "f2f_message": ("Multiline text", "What was found"), "f2f_sourcepages": ("Text", "Packet pages")}},
    "f2f_fieldvalue": {
        "display": "Extracted field", "primary": "f2f_fieldvalueid",
        "columns": {"f2f_fieldvalueid": ("Text", "Field value ID"), "f2f_fileid": ("Lookup", "Intake file"),
                    "f2f_document": ("Choice", "Document type"), "f2f_documentindex": ("Whole number", "Document number"),
                    "f2f_field": ("Text", "Field"), "f2f_value": ("Text", "Value as read"),
                    "f2f_sourcepage": ("Whole number", "Packet page"), "f2f_sourceline": ("Text", "Line read"),
                    "f2f_confidence": ("Decimal", "Confidence 0 to 1"),
                    "f2f_validated": ("Yes/No", "Proved by a cross check"),
                    "f2f_needsreview": ("Yes/No", "Sent to a person")}},
}


def _fields(fid: str, doc: str, idx: int, d: dict, review: set) -> list[dict]:
    rows = []
    for k, v in d.items():
        if not isinstance(v, dict) or "value" not in v:
            continue
        cite = v.get("cite") or {}
        conf = 0.99 if v.get("validated") else cite.get("conf", 0.0)
        name = f"{doc}.{k}"
        rows.append({"f2f_fieldvalueid": f"{fid}-{doc}-{idx}-{k}", "f2f_fileid": fid, "f2f_document": doc,
                     "f2f_documentindex": idx, "f2f_field": k,
                     "f2f_value": "" if v["value"] is None else str(v["value"]),
                     "f2f_sourcepage": cite.get("page"), "f2f_sourceline": cite.get("line", ""),
                     "f2f_confidence": round(float(conf or 0), 3), "f2f_validated": bool(v.get("validated")),
                     "f2f_needsreview": name in review or (conf or 0) < 0.80})
    return rows


def build(extractor: str = "layout-v2") -> dict[str, pd.DataFrame]:
    files, inc, cred, find, vals = [], [], [], [], []
    for line in (WORK / f"extract.{extractor}.jsonl").read_text().splitlines():
        d = json.loads(line)
        e, r = d["extraction"], d["result"]
        fid = r["file_id"]
        f, s = r["figures"], r.get("surplus") or {}
        checks = [x for x in r["findings"] if x["severity"] == "check"]
        files.append({"f2f_fileid": fid, "f2f_extractor": r["extractor"],
                      "f2f_status": "needs review" if checks or r["review_fields"] else "ready",
                      "f2f_persons": f["persons"], "f2f_debtornetmonthly": f["debtor_monthly"],
                      "f2f_spousenetmonthly": f["spouse_monthly"], "f2f_unsecuredtotal": f["unsecured_total"],
                      "f2f_checks": len(checks), "f2f_fieldstoreview": len(r["review_fields"])})
        if s:
            inc.append({"f2f_fileid": fid, "f2f_line1debtornetincome": s.get("line1_debtor_net_income"),
                        "f2f_line2othermembersnetincome": s.get("line2_other_members_net_income"),
                        "f2f_line3familynetincome": s.get("line3_family_net_income"),
                        "f2f_line6familynondiscretionary": s.get("line6_family_non_discretionary"),
                        "f2f_line8familyavailable": s.get("line8_family_available"),
                        "f2f_line9debtorsharepct": s.get("line9_debtor_share_pct"),
                        "f2f_standard": s.get("standard"), "f2f_familysurplus": s.get("family_surplus"),
                        "f2f_line15monthlypayment": s.get("line15_monthly_payment"),
                        "f2f_steps": " | ".join(s.get("steps", []))})
        for i, c in enumerate(r["creditors"]):
            cred.append({"f2f_creditorid": f"{fid}-C{i + 1}", "f2f_fileid": fid, "f2f_name": c["name"],
                         "f2f_accountlast4": c.get("last4") or "", "f2f_balance": c["balance"],
                         "f2f_source": c["source"], "f2f_sourcepage": c.get("page")})
        for i, x in enumerate(r["findings"]):
            find.append({"f2f_findingid": f"{fid}-K{i + 1}", "f2f_fileid": fid, "f2f_code": x["code"],
                         "f2f_severity": x["severity"], "f2f_message": x["message"],
                         "f2f_sourcepages": ",".join(str(p) for p in x["pages"] if p)})
        review = {x["field"] for x in r["review_fields"]}
        vals += _fields(fid, "intake", 1, e["intake"], review)
        for j, st in enumerate(e["stubs"], 1):
            vals += _fields(fid, "stub", j, st, review)
        for j, lt in enumerate(e["letters"], 1):
            vals += _fields(fid, "letter", j, lt, review)
        for j, t in enumerate(e["tradelines"], 1):
            vals += _fields(fid, "tradeline", j, t, review)
        vals += _fields(fid, "benefit", 1, e["benefit"], review)
    return {"f2f_intakefile": pd.DataFrame(files), "f2f_incomeexpense": pd.DataFrame(inc),
            "f2f_creditor": pd.DataFrame(cred), "f2f_finding": pd.DataFrame(find), "f2f_fieldvalue": pd.DataFrame(vals)}


def export(extractor: str = "layout-v2", out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    tables = build(extractor)
    counts = {}
    for name, df in tables.items():
        cols = list(SCHEMA[name]["columns"])
        df = df.reindex(columns=cols)
        df.to_csv(out / f"{name}.csv", index=False)
        (out / f"{name}.json").write_text(df.to_json(orient="records", indent=1))
        counts[name] = int(len(df))
    schema = {t: {"display_name": v["display"], "primary_column": v["primary"],
                  "columns": [{"logical_name": c, "type": ty, "display_name": dn} for c, (ty, dn) in v["columns"].items()]}
              for t, v in SCHEMA.items()}
    (out / "schema.json").write_text(json.dumps({"publisher_prefix": PREFIX, "tables": schema}, indent=1))
    return counts


if __name__ == "__main__":
    print(export(sys.argv[1] if len(sys.argv) > 1 else "layout-v2"))
