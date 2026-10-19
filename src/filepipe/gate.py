"""Release gate for extractor versions. Same rules locally, in Docker and in CI.

python -m filepipe.gate                       gate the configured candidate on the current batch
python -m filepipe.gate --packets 30          build a fresh small batch first (what CI does)
python -m filepipe.gate --candidate layout-v2-fastocr --expect-block   negative control
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from filepipe.config import CONFIGS, PACKETS, RESULTS


def load_rules() -> dict:
    return yaml.safe_load((CONFIGS / "release.yaml").read_text())


def decide(prod: dict, cand: dict, rules: dict) -> dict:
    reasons = []
    if cand["field_accuracy"] < prod["field_accuracy"] - rules["max_field_accuracy_drop"]:
        reasons.append(f"field accuracy {cand['field_accuracy']} vs {prod['field_accuracy']}")
    if cand["auto_accepted_error_rate"] > rules["max_auto_accepted_error_rate"]:
        reasons.append(f"auto accepted error rate {cand['auto_accepted_error_rate']} above {rules['max_auto_accepted_error_rate']}")
    if rules["trap_recall_may_not_drop"] and cand["trap_recall"] < prod["trap_recall"]:
        reasons.append(f"trap recall {cand['trap_recall']} vs {prod['trap_recall']}")
    if rules["surplus_exact_may_not_drop"] and cand["surplus_payment_exact"] < prod["surplus_payment_exact"]:
        reasons.append(f"surplus exact {cand['surplus_payment_exact']} vs {prod['surplus_payment_exact']}")
    if rules["silent_wrong_files_may_not_rise"] and cand["files_wrong_and_not_flagged"] > prod["files_wrong_and_not_flagged"]:
        reasons.append(f"files wrong and not flagged {cand['files_wrong_and_not_flagged']} vs {prod['files_wrong_and_not_flagged']}")
    if cand["seconds_median"] > rules["max_median_seconds"]:
        reasons.append(f"median seconds {cand['seconds_median']}")
    return {"decision": "block" if reasons else "promote", "reasons": reasons}


def log_mlflow(report: dict, decisions: dict) -> None:
    try:
        import mlflow

        from filepipe.config import mlflow_uri
        mlflow.set_tracking_uri(mlflow_uri())
        mlflow.set_experiment("packet-extraction")
        for name, m in report.items():
            with mlflow.start_run(run_name=name):
                mlflow.log_param("extractor", name)
                mlflow.log_metrics({k: float(v) for k, v in m.items() if isinstance(v, (int, float))})
                if name in decisions:
                    mlflow.set_tag("gate", decisions[name]["decision"])
    except Exception as e:  # tracking is a nice to have; the gate result file is the record
        print("mlflow logging skipped:", e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets", type=int, default=0, help="build a fresh batch of this size first")
    ap.add_argument("--candidate", default=None)
    ap.add_argument("--expect-block", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_rules()["extraction"]
    cand = a.candidate or cfg["candidate"]
    from filepipe.extract_run import run_ocr, run_versions
    if a.packets:
        from filepipe.synth.build import build_batch
        build_batch(n=a.packets, seed=101)
        import shutil
        from filepipe.config import WORK
        shutil.rmtree(WORK / "ocr", ignore_errors=True)
    setups = ("full", "fast") if "fastocr" in cand or a.packets == 0 else ("full",)
    run_ocr(PACKETS, setups=setups)
    report = run_versions(PACKETS, versions=[cfg["production"], cand])
    d = decide(report[cfg["production"]], report[cand], cfg["rules"])
    out = {"production": cfg["production"], "candidate": cand, **d,
           "production_metrics": {k: v for k, v in report[cfg["production"]].items() if not isinstance(v, dict)},
           "candidate_metrics": {k: v for k, v in report[cand].items() if not isinstance(v, dict)}}
    if not a.no_mlflow:
        log_mlflow(report, {cand: d})
    Path(RESULTS).mkdir(parents=True, exist_ok=True)
    (RESULTS / f"gate_extraction_{cand}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("production", "candidate", "decision", "reasons")}, indent=1))
    if a.expect_block:
        return 0 if d["decision"] == "block" else 1
    return 0 if d["decision"] == "promote" else 1


if __name__ == "__main__":
    sys.exit(main())
