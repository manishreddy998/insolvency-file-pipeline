import json

import pandas as pd

import filepipe.export_dataverse as dv


def test_export_from_one_file(tmp_path, monkeypatch):
    rec = {"extraction": {"intake": {"stated_income": {"value": 2000.0, "cite": {"page": 1, "line": "Your monthly take home pay: $2,000.00", "conf": 0.95}, "validated": False}},
                          "stubs": [{"net": {"value": 1000.0, "cite": {"page": 2, "line": "Net Pay: $1,000.00", "conf": 0.7}, "validated": True}, "page": 2}],
                          "letters": [], "tradelines": [], "benefit": {}},
           "result": {"file_id": "F1", "extractor": "layout-v2", "review_fields": [{"field": "intake.stated_income"}],
                      "figures": {"persons": 1, "debtor_monthly": 2166.67, "spouse_monthly": 0.0, "unsecured_total": 500.0},
                      "surplus": {"line1_debtor_net_income": 2166.67, "line15_monthly_payment": 0.0, "steps": ["a", "b"]},
                      "creditors": [{"name": "Bank", "last4": "1111", "balance": 500.0, "source": "credit_report", "page": 3}],
                      "findings": [{"code": "stale_stub", "severity": "check", "message": "m", "pages": [2, None]}]}}
    (tmp_path / "extract.layout-v2.jsonl").write_text(json.dumps(rec) + "\n")
    monkeypatch.setattr(dv, "WORK", tmp_path)
    counts = dv.export(out=tmp_path / "out")
    assert counts == {"f2f_intakefile": 1, "f2f_incomeexpense": 1, "f2f_creditor": 1, "f2f_finding": 1, "f2f_fieldvalue": 2}
    fv = pd.read_csv(tmp_path / "out" / "f2f_fieldvalue.csv")
    assert set(fv["f2f_sourcepage"]) == {1, 2}
    row = fv.set_index("f2f_field").loc["stated_income"]
    assert bool(row["f2f_needsreview"]) and not bool(row["f2f_validated"])
    assert fv.set_index("f2f_field").loc["net"]["f2f_confidence"] == 0.99
    schema = json.loads((tmp_path / "out" / "schema.json").read_text())
    for t, v in schema["tables"].items():
        assert t.startswith("f2f_")
        assert list(pd.read_csv(tmp_path / "out" / f"{t}.csv").columns) == [c["logical_name"] for c in v["columns"]]
