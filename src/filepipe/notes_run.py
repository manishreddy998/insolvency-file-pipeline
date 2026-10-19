"""Write the trustee note for every file and count what the claim checker removed."""
from __future__ import annotations

import json
import statistics
import sys
import time
from types import SimpleNamespace

from filepipe.claims import check_note
from filepipe.config import RESULTS, WORK
from filepipe.narrate import get_writer, note_for


def results(extractor: str = "layout-v2") -> list[SimpleNamespace]:
    rows = []
    for line in (WORK / f"extract.{extractor}.jsonl").read_text().splitlines():
        r = json.loads(line)["result"]
        rows.append(SimpleNamespace(**r))
    return rows


def run(mode: str = "model", limit: int | None = None) -> dict:
    writer = get_writer(mode)
    if mode != "template" and writer is None:
        raise SystemExit(f"writer '{mode}' is not available (is the llm service up?)")
    rows = results()[:limit] if limit else results()
    out, secs = [], []
    for res in rows:
        t = time.time()
        n = note_for(res, writer)
        secs.append(time.time() - t)
        recheck = check_note(n["note"], n["facts"])  # the final note must pass its own check
        n["final_unsupported"] = sum(len(d["unsupported"]) for d in recheck["dropped"])
        n["file_id"] = res.file_id
        out.append(n)
    (WORK / f"notes.{mode}.jsonl").write_text("\n".join(json.dumps(n, default=str) for n in out) + "\n")
    dropped = [d for n in out for d in n["dropped"]]
    summary = {
        "writer": mode, "files": len(out),
        "notes_with_a_sentence_removed": sum(bool(n["dropped"]) for n in out),
        "sentences_removed": len(dropped),
        "unsupported_claims_removed": sum(len(d["unsupported"]) for d in dropped),
        "fell_back_to_template": sum(bool(n.get("fell_back")) for n in out),
        "unsupported_claims_in_final_notes": sum(n["final_unsupported"] for n in out),
        "seconds_per_note_median": round(statistics.median(secs), 3) if secs else 0.0,
        "examples_removed": [d["sentence"] for d in dropped[:5]],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"notes_{mode}.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "model"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    s = run(mode, lim)
    print(json.dumps(s, indent=1))
    sys.exit(1 if s["unsupported_claims_in_final_notes"] else 0)
