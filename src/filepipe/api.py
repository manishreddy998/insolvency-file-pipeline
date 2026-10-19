"""Small API: send a packet, get the checked file back; read files, the review queue and the radar."""
from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile

from filepipe.config import WORK
from filepipe.extract import get_extractor
from filepipe.narrate import get_writer, note_for
from filepipe.ocr import read_packet
from filepipe.verify import verify

app = FastAPI(title="File to Finish", version="0.1",
              description="Synthetic intake packets in, checked Form 65 figures and a trustee note out.")
PRODUCTION = "layout-v2"
UPLOADS = WORK / "uploads"


def _files() -> dict:
    p = WORK / f"extract.{PRODUCTION}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            r = json.loads(line)["result"]
            out[r["file_id"]] = r
    if UPLOADS.exists():
        for f in UPLOADS.glob("*.json"):
            r = json.loads(f.read_text())
            out[r["file_id"]] = r
    return out


@app.get("/health")
def health() -> dict:
    return {"ok": True, "extractor": PRODUCTION, "files": len(_files())}


@app.post("/packets")
async def post_packet(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "send a PDF packet")
    fid = "U" + uuid.uuid4().hex[:8].upper()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "packet.pdf"
        p.write_bytes(await file.read())
        fx = get_extractor(PRODUCTION).extract(fid, read_packet(p))
    res = verify(fx)
    note = note_for(res, get_writer("model"))
    out = {**asdict(res), "note": note["note"], "note_writer": note["writer"],
           "note_sentences_removed": len(note["dropped"]), "seconds": round(fx.seconds + fx.ocr.get("ocr_seconds", 0), 2)}
    UPLOADS.mkdir(parents=True, exist_ok=True)
    (UPLOADS / f"{fid}.json").write_text(json.dumps(out, default=str))
    return out


@app.get("/files/{file_id}")
def get_file(file_id: str) -> dict:
    r = _files().get(file_id)
    if not r:
        raise HTTPException(404, "no such file")
    return r


@app.get("/review-queue")
def review_queue(limit: int = 50) -> list[dict]:
    rows = []
    for r in _files().values():
        checks = [f["code"] for f in r["findings"] if f["severity"] == "check"]
        if checks or r["review_fields"]:
            rows.append({"file_id": r["file_id"], "checks": checks, "fields_to_review": len(r["review_fields"]),
                         "monthly_payment": (r.get("surplus") or {}).get("line15_monthly_payment")})
    return sorted(rows, key=lambda x: (-len(x["checks"]), -x["fields_to_review"]))[:limit]


@app.get("/radar")
def radar(limit: int = 25) -> list[dict]:
    p = WORK / "radar_scores.csv"
    if not p.exists():
        raise HTTPException(404, "radar has not run")
    df = pd.read_csv(p).head(limit).fillna("")
    return df.to_dict(orient="records")
