"""Run every step in order. Dagster calls the same functions; this is the plain command line way.

python -m filepipe.pipeline            full run (300 packets)
python -m filepipe.pipeline --small    24 packets, for a quick check
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time

from filepipe.config import DATA, PACKETS, RESULTS, WORK, database_url, ensure_dirs


def step_packets(n: int = 300, seed: int = 7, reuse: bool = True) -> dict:
    from filepipe.extract_run import manifest
    from filepipe.synth.build import build_batch
    if reuse and (PACKETS / "manifest.jsonl").exists() and len(manifest()) == n:
        return {"packets": n, "built": False}
    shutil.rmtree(PACKETS, ignore_errors=True)
    shutil.rmtree(WORK / "ocr", ignore_errors=True)
    build_batch(n=n, seed=seed)
    return {"packets": n, "built": True}


def step_ocr() -> dict:
    from filepipe.extract_run import run_ocr
    return run_ocr(PACKETS, setups=("full", "fast"))


def step_extract() -> dict:
    from filepipe.extract_run import run_versions
    rep = run_versions()
    return {k: {m: v[m] for m in ("field_accuracy", "trap_recall", "files_wrong_and_not_flagged")} for k, v in rep.items()}


def step_gates(use_mlflow: bool = True) -> dict:
    from filepipe.gate import main as gate
    args = [] if use_mlflow else ["--no-mlflow"]
    promote = gate(args)
    block = gate(args + ["--candidate", "layout-v2-fastocr", "--expect-block"])
    if promote or block:
        raise RuntimeError("extraction gate did not behave: candidate must promote and negative control must block")
    return {"layout-v2": "promote", "layout-v2-fastocr": "block"}


def step_notes() -> dict:
    from filepipe.narrate import get_writer
    from filepipe.notes_run import run
    hostile = run("hostile")
    if hostile["unsupported_claims_in_final_notes"]:
        raise RuntimeError("hostile writer got an unsupported claim through")
    mode = "model" if get_writer("model") else "template"
    return {"hostile": hostile, "notes": run(mode)}


def step_radar(use_mlflow: bool = True) -> dict:
    from filepipe.radar.model import run
    r = run(use_mlflow=use_mlflow)
    return {"gate": r["gate"], "scored_with": r["scored_with"]}


def step_leads() -> dict:
    from filepipe.leads.funnel import run
    r = run()
    return {"resolver": r["identity_resolver"], "baseline": r["identity_baseline_exact_email_or_phone"]}


def step_demand() -> dict:
    from filepipe.demand import run
    from filepipe.fetch_osb import fetch
    fetch()
    r = run()
    return {k: r[k] for k in ("months", "chosen_forecaster", "ytd_share_in_office_fsas")}


def step_azure() -> dict:
    from filepipe.azure_di import side_by_side
    r = side_by_side(use_mlflow=False)
    return r if "skipped" in r else {k: r[k] for k in ("subset_files", "subset_pages", "decision", "reasons")}


def step_export() -> dict:
    from filepipe.export_dataverse import export
    return export()


def step_warehouse() -> dict:
    if not database_url():
        return {"skipped": "DATABASE_URL not set"}
    from filepipe.load import load
    counts = load()
    p = subprocess.run(["dbt", "build", "--project-dir", "dbt", "--target-path", "/tmp/dbt-target",
                        "--log-path", "/tmp/dbt-logs"], capture_output=True, text=True)
    tail = p.stdout.strip().splitlines()[-1:] if p.stdout else []
    if p.returncode:
        raise RuntimeError("dbt build failed:\n" + p.stdout[-3000:])
    return {"rows": counts, "dbt": tail}


def scoreboard() -> dict:
    """One file with the headline numbers, read from the results each step wrote."""
    def j(name):
        p = RESULTS / name
        return json.loads(p.read_text()) if p.exists() else {}
    ex, radar, fun, dem = j("extraction_eval.json"), j("radar_eval.json"), j("funnel.json"), j("demand.json")
    notes = j("notes_model.json") or j("notes_template.json")
    out = {"extraction": {k: {m: v.get(m) for m in ("field_accuracy", "auto_accepted_error_rate", "review_share",
                                                     "surplus_payment_exact", "file_figures_all_exact",
                                                     "files_wrong_and_not_flagged", "trap_recall", "trap_false_alarms",
                                                     "seconds_median")} for k, v in ex.items()},
           "notes": notes, "hostile": j("notes_hostile.json"),
           "radar": {k: {m: v.get(m) for m in ("auc", "recall_at_workload", "overdue_rule_recall",
                                                "recall_at_2pct", "overdue_rule_recall_at_2pct",
                                                "flagged_before_any_arrears_share")}
                     for k, v in radar.get("report", {}).items() if not k.startswith("_")},
           "radar_gate": radar.get("gate"),
           "identity": {"resolver": fun.get("identity_resolver"), "baseline": fun.get("identity_baseline_exact_email_or_phone")},
           "demand": {k: dem.get(k) for k in ("months", "backtest", "ytd_consumer_insolvencies_ex_quebec",
                                              "ytd_share_in_office_fsas", "sheet_total_checks_passed")}}
    (RESULTS / "summary.json").write_text(json.dumps(out, indent=1))
    return out


STEPS = ["packets", "ocr", "extract", "gates", "azure", "notes", "export", "radar", "leads", "demand", "warehouse"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", action="store_true", help="24 packets instead of 300")
    ap.add_argument("--only", nargs="*", choices=STEPS)
    ap.add_argument("--no-mlflow", action="store_true")
    a = ap.parse_args(argv)
    ensure_dirs()
    n = 24 if a.small else 300
    plan = a.only or STEPS
    timings = {}
    for s in plan:
        t = time.time()
        fn = {"packets": lambda: step_packets(n), "ocr": step_ocr, "extract": step_extract,
              "gates": lambda: step_gates(not a.no_mlflow), "notes": step_notes,
              "radar": lambda: step_radar(not a.no_mlflow), "leads": step_leads, "demand": step_demand,
              "warehouse": step_warehouse, "azure": step_azure, "export": step_export}[s]
        r = fn()
        timings[s] = round(time.time() - t, 1)
        print(f"[{s}] {timings[s]}s {json.dumps(r, default=str)[:300]}", flush=True)
    scoreboard()
    (RESULTS / "timings.json").write_text(json.dumps({"packets": n, "seconds": timings, "data": str(DATA)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
