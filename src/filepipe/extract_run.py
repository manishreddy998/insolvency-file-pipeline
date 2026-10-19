"""Read every packet once per OCR setup, run each extractor version, verify and score."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from filepipe.config import PACKETS, RESULTS, WORK
from filepipe.evaluate import evaluate
from filepipe.extract import get_extractor
from filepipe.ocr import Line, OcrConfig, PacketText, read_packet
from filepipe.verify import verify

VERSIONS = ["labels-v1", "layout-v2", "layout-v2-fastocr"]


def _ocr_one(args) -> str:
    path, setup, out = args
    if out.exists():
        return str(out)
    cfg = OcrConfig.fast() if setup == "fast" else OcrConfig()
    pt = read_packet(path, cfg)
    out.write_text(json.dumps({"lines": [asdict(l) for l in pt.lines], "features": pt.features}))
    return str(out)


def load_ocr(p: Path) -> PacketText:
    d = json.loads(p.read_text())
    return PacketText([Line(**l) for l in d["lines"]], d["features"])


def manifest(packets: Path = PACKETS) -> list[dict]:
    return [json.loads(l) for l in (packets / "manifest.jsonl").read_text().splitlines()]


def run_ocr(packets: Path = PACKETS, setups=("full", "fast"), workers: int | None = None) -> dict:
    out_dir = WORK / "ocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = manifest(packets)
    jobs = [(packets / r["path"], s, out_dir / f"{r['file_id']}.{s}.json") for s in setups for r in rows]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as ex:
        list(ex.map(_ocr_one, jobs, chunksize=1))
    return {"packets": len(rows), "setups": list(setups), "seconds": round(time.perf_counter() - t0, 1)}


def run_versions(packets: Path = PACKETS, versions=VERSIONS, write_report: bool = True) -> dict:
    rows = manifest(packets)
    report = {}
    RESULTS.mkdir(parents=True, exist_ok=True)
    for name in versions:
        ex = get_extractor(name)
        setup = "fast" if getattr(ex, "ocr", "full") == "fast" else "full"
        triples = []
        out = WORK / f"extract.{name}.jsonl"
        with out.open("w") as fh:
            for m in rows:
                pt = load_ocr(WORK / "ocr" / f"{m['file_id']}.{setup}.json")
                fx = ex.extract(m["file_id"], pt)
                res = verify(fx)
                triples.append((m, fx, res))
                fh.write(json.dumps({"extraction": fx.to_dict(), "result": asdict(res)}, default=str) + "\n")
        report[name] = evaluate(triples)
    if write_report:
        (RESULTS / "extraction_eval.json").write_text(json.dumps(report, indent=1))
    return report
