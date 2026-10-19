"""Build a batch of synthetic client packets with an answer key per packet."""
from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from filepipe.config import PACKETS
from filepipe.synth.degrade import degrade_pdf
from filepipe.synth.households import make_cohort
from filepipe.synth.render import build_pages, draw_pdf

CAPTURE_MIX = {"digital": 0.40, "scan": 0.30, "fax": 0.15, "phone": 0.15}


def _one(args) -> dict:
    h, out_dir, seed = args
    rng = random.Random(seed)
    mode = rng.choices(list(CAPTURE_MIX), list(CAPTURE_MIX.values()))[0]
    pages = build_pages(h, rng)
    clean = out_dir / f"{h.file_id}.digital.pdf"
    draw_pdf(pages, clean)
    path = clean
    if mode != "digital":
        path = out_dir / f"{h.file_id}.{mode}.pdf"
        degrade_pdf(clean, path, mode, rng)
        clean.unlink()
    return {"file_id": h.file_id, "path": path.name, "capture": mode,
            "pages": [{"kind": p.kind} for p in pages], "answer": h.answer_key()}


def build_batch(n: int = 300, seed: int = 7, out_dir: Path | None = None, workers: int = 8,
                trap_rate: float = 0.55) -> Path:
    out_dir = Path(out_dir or PACKETS)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("F*.pdf"):
        old.unlink()
    cohort = make_cohort(n, seed, trap_rate)
    jobs = [(h, out_dir, seed * 100003 + i) for i, h in enumerate(cohort)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_one, jobs, chunksize=4))
    manifest = out_dir / "manifest.jsonl"
    with manifest.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(PACKETS))
    a = ap.parse_args()
    print(build_batch(a.n, a.seed, Path(a.out)))


if __name__ == "__main__":
    main()
