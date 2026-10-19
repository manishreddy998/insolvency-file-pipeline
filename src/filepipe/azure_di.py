"""Azure AI Document Intelligence as a second text reader behind the same extractor interface.

The service reads the PDF (model prebuilt-read by default, prebuilt-layout also works). We rebuild visual rows
from its word positions, the same way the Tesseract path does, and hand the text to the same parsing and
proof checks. So the only thing that changes between the two extractors is who reads the page.

Settings come from the environment only: AZURE_DI_ENDPOINT, AZURE_DI_KEY, optional AZURE_DI_MODEL.
The free F0 tier allows 500 pages a month, so every call is cached under data/work/azure and a page budget
is enforced before anything is sent. With no settings the Azure extractor is skipped and nothing is called.
"""
from __future__ import annotations

import io
import json
import math
import os
import time
from datetime import date
from pathlib import Path

import numpy as np

from filepipe.config import PACKETS, RESULTS, WORK
from filepipe.ocr import Line, PacketText

CACHE = WORK / "azure"
RUN_PAGE_CAP = int(os.environ.get("AZURE_DI_RUN_PAGES", "150"))
MONTH_PAGE_CAP = int(os.environ.get("AZURE_DI_MONTH_PAGES", "450"))  # under the 500 page F0 limit
SUBSET_SEED = 2026


class BudgetExceeded(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("AZURE_DI_ENDPOINT")) and bool(os.environ.get("AZURE_DI_KEY"))


def model_id() -> str:
    return os.environ.get("AZURE_DI_MODEL", "prebuilt-read")


def make_client():
    """The real client. Imported late so the package is only needed when Azure is used."""
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    return DocumentIntelligenceClient(os.environ["AZURE_DI_ENDPOINT"], AzureKeyCredential(os.environ["AZURE_DI_KEY"]))


# page budget ---------------------------------------------------------------------------------------------
def _usage_path() -> Path:
    return CACHE / "usage.json"


def pages_used_this_month() -> int:
    p = _usage_path()
    if not p.exists():
        return 0
    return int(json.loads(p.read_text()).get(date.today().strftime("%Y-%m"), 0))


def _add_usage(pages: int) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = _usage_path()
    u = json.loads(p.read_text()) if p.exists() else {}
    k = date.today().strftime("%Y-%m")
    u[k] = int(u.get(k, 0)) + pages
    p.write_text(json.dumps(u, indent=1))


# reading ---------------------------------------------------------------------------------------------------
def cache_path(file_id: str) -> Path:
    return CACHE / f"{file_id}.{model_id()}.json"


def analyze(pdf: Path, file_id: str, n_pages: int, client=None, run_pages: list | None = None) -> dict:
    """Return the service result as a dict, from cache when we have it. run_pages counts pages sent this run."""
    cp = cache_path(file_id)
    if cp.exists():
        return json.loads(cp.read_text())
    sent = sum(run_pages) if run_pages is not None else 0
    if sent + n_pages > RUN_PAGE_CAP:
        raise BudgetExceeded(f"run cap of {RUN_PAGE_CAP} pages reached")
    if pages_used_this_month() + n_pages > MONTH_PAGE_CAP:
        raise BudgetExceeded(f"monthly cap of {MONTH_PAGE_CAP} pages reached")
    client = client or make_client()
    t0 = time.perf_counter()
    # The free F0 tier only analyses the first two pages of a document, so send one page per call.
    import pymupdf
    src = pymupdf.open(pdf)
    merged: list = []
    for i in range(len(src)):
        one = pymupdf.open()
        one.insert_pdf(src, from_page=i, to_page=i)
        poller = client.begin_analyze_document(model_id(), body=io.BytesIO(one.tobytes()),
                                               content_type="application/octet-stream")
        res = poller.result()
        r = res.as_dict() if hasattr(res, "as_dict") else dict(res)
        for pg in r.get("pages", []):
            pg = dict(pg)
            pg["pageNumber"] = i + 1
            merged.append(pg)
    out = {"pages": merged, "_seconds": round(time.perf_counter() - t0, 3)}
    out["_model"] = model_id()
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(out))
    _add_usage(n_pages)
    if run_pages is not None:
        run_pages.append(n_pages)
    return out


def _rotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    a = math.radians(-angle_deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def to_packet(result: dict) -> PacketText:
    """Words with positions become visual rows, so a label and the value to its right share one line."""
    lines: list[Line] = []
    page_confs = []
    for pg in sorted(result.get("pages", []), key=lambda p: p.get("pageNumber", 0)):
        pno = int(pg.get("pageNumber", 1)) - 1
        angle = float(pg.get("angle") or 0.0)
        words = []
        for w in pg.get("words", []):
            poly = w.get("polygon") or []
            if len(poly) < 8 or not w.get("content", "").strip():
                continue
            xs, ys = poly[0::2], poly[1::2]
            cx, cy = _rotate(float(np.mean(xs)), float(np.mean(ys)), angle)
            lx, _ = _rotate(min(xs), float(np.mean(ys)), angle)
            h = max(ys) - min(ys)
            words.append([cy, lx, h, w["content"], float(w.get("confidence", 0.0)) * 100])
        if not words:
            page_confs.append(0.0)
            continue
        tol = max(float(np.median([w[2] for w in words])) * 0.6, 1e-3)
        rows: list[tuple[float, list]] = []
        for w in sorted(words):
            if rows and abs(rows[-1][0] - w[0]) < tol:
                rows[-1][1].append(w)
            else:
                rows.append((w[0], [w]))
        for _, ws in rows:
            ws.sort(key=lambda w: w[1])
            lines.append(Line(" ".join(w[3] for w in ws), float(np.mean([w[4] for w in ws])), pno))
        page_confs.append(float(np.mean([w[4] for w in words])))
    feats = {"n_pages": len(result.get("pages", [])), "ocr_seconds": float(result.get("_seconds", 0.0)),
             "engine": f"azure-di:{result.get('_model', model_id())}", "page_confs": page_confs,
             "mean_conf": float(np.mean(page_confs)) if page_confs else 0.0}
    return PacketText(lines, feats)


# held out subset --------------------------------------------------------------------------------------------
def subset(rows: list[dict], page_cap: int = RUN_PAGE_CAP) -> list[dict]:
    """Scanned, faxed and phone packets only (digital PDFs have a text layer), mixed evenly, under the cap."""
    import random
    rng = random.Random(SUBSET_SEED)
    by = {c: [r for r in rows if r["capture"] == c] for c in ("scan", "fax", "phone")}
    for v in by.values():
        rng.shuffle(v)
    out, pages = [], 0
    while any(by.values()):
        for c in ("scan", "fax", "phone"):
            if not by[c]:
                continue
            r = by[c].pop()
            n = len(r["pages"])
            if pages + n > page_cap:
                return out
            out.append(r)
            pages += n
    return out


def run_azure_ocr(rows: list[dict], client=None, packets: Path = PACKETS) -> dict:
    sent: list[int] = []
    done = cached = 0
    for r in rows:
        had = cache_path(r["file_id"]).exists()
        analyze(packets / r["path"], r["file_id"], len(r["pages"]), client=client, run_pages=sent)
        done += 1
        cached += had
    return {"files": done, "from_cache": cached, "pages_sent": sum(sent), "pages_used_this_month": pages_used_this_month()}


def side_by_side(client=None, use_mlflow: bool = True) -> dict:
    """Read the held out subset with Azure, then score both extractors on the same files with the same harness."""
    from filepipe.evaluate import evaluate
    from filepipe.extract import get_extractor
    from filepipe.extract_run import load_ocr, manifest
    from filepipe.gate import decide, load_rules
    from filepipe.verify import verify

    try:
        rows = subset(manifest())
    except FileNotFoundError:
        rows = []
    have_cache = bool(rows) and all(cache_path(r["file_id"]).exists() for r in rows)
    if not configured() and client is None and not have_cache:
        out = {"skipped": "AZURE_DI_ENDPOINT and AZURE_DI_KEY are not set"}
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "azure_side_by_side.json").write_text(json.dumps(out, indent=1))
        return out
    usage = run_azure_ocr(rows, client=client)
    report = {}
    for name, load in (("layout-v2", lambda r: load_ocr(WORK / "ocr" / f"{r['file_id']}.full.json")),
                       ("azure-di-layout", lambda r: to_packet(json.loads(cache_path(r["file_id"]).read_text())))):
        ex = get_extractor(name)
        triples = []
        for r in rows:
            fx = ex.extract(r["file_id"], load(r))
            triples.append((r, fx, verify(fx)))
        report[name] = evaluate(triples)
    rules = load_rules()["extraction"]["rules"]
    d = decide(report["layout-v2"], report["azure-di-layout"], rules)
    out = {"subset_files": len(rows), "subset_pages": sum(len(r["pages"]) for r in rows),
           "captures": {c: sum(r["capture"] == c for r in rows) for c in ("scan", "fax", "phone")},
           "model": model_id(), "usage": usage, "production": "layout-v2", "candidate": "azure-di-layout", **d,
           "metrics": {k: {m: v for m, v in r.items() if not isinstance(v, dict)} for k, r in report.items()},
           "by_capture": {k: r.get("by_capture") for k, r in report.items()}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "azure_side_by_side.json").write_text(json.dumps(out, indent=1))
    if use_mlflow:
        from filepipe.gate import log_mlflow
        log_mlflow(report, {"azure-di-layout": d})
    return out


if __name__ == "__main__":
    import sys
    r = side_by_side(use_mlflow="--no-mlflow" not in sys.argv)
    print(json.dumps({k: v for k, v in r.items() if k != "by_capture"}, indent=1))
