"""Print every field the reader got wrong, with the line it read. A development aid."""
import json
import sys

from filepipe.evaluate import _eq, _pairs
from filepipe.extract.base import Value
from filepipe.extract_run import load_ocr, manifest
from filepipe.config import WORK
from filepipe.extract import get_extractor
from filepipe.verify import verify

name = sys.argv[1] if len(sys.argv) > 1 else "layout-v2"
only = sys.argv[2] if len(sys.argv) > 2 else None
ex = get_extractor(name)
setup = "fast" if getattr(ex, "ocr", "full") == "fast" else "full"
for m in manifest():
    fx = ex.extract(m["file_id"], load_ocr(WORK / "ocr" / f"{m['file_id']}.{setup}.json"))
    res = verify(fx)
    for f, v, t in _pairs(fx, res, m["answer"]):
        got = v.value if isinstance(v, Value) else None
        if not _eq(got, t) and (not only or only in f):
            print(m["file_id"], m["capture"], f, "got", repr(got), "want", repr(t), "|", v.cite.line if isinstance(v, Value) and v.cite else "-", "| conf", round(v.conf, 2) if isinstance(v, Value) else "-")
    k = m["answer"]
    for f in ("debtor_monthly", "spouse_monthly", "persons", "unsecured_total"):
        if not _eq(res.figures[f], k[f]):
            print(m["file_id"], m["capture"], "FIGURE", f, res.figures[f], "want", k[f])
    planted = set(m["answer"]["traps"]); found = {x["code"] for x in res.findings}
    if planted - found:
        print(m["file_id"], m["capture"], "MISSED", planted - found, fx.bank.get("pages_seen"), fx.bank.get("pages_declared"))
