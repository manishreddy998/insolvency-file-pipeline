"""Score extractions and proof checks against the answer key."""
from __future__ import annotations

from collections import defaultdict

from filepipe.extract.base import Value
from filepipe.extract.parse import same_name
from filepipe.verify import REVIEW_CONF, TRAP_CODES


def _eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(b, float) or isinstance(a, float):
        try:
            return abs(float(a) - float(b)) < 0.011
        except (TypeError, ValueError):
            return False
    if isinstance(b, str):
        return str(a).strip().lower() == b.strip().lower()
    return a == b


def _pairs(fx, res, key) -> list[tuple]:
    """(field, Value or None, truth) for every field the answer key can check."""
    it = fx.intake
    out = [("intake.name", it.get("name"), f"{key['first']} {key['last']}"),
           ("intake.postal", it.get("postal"), key["postal"]),
           ("intake.persons", it.get("persons"), key["stated_persons"]),
           ("intake.stated_income", it.get("stated_income"), key["stated_income"]),
           ("intake.stated_support", it.get("stated_support"), key["stated_support"]),
           ("intake.child_care", it.get("child_care"), key["child_care"]),
           ("intake.medical", it.get("medical"), key["medical"]),
           ("intake.rent", it.get("rent"), key["rent"]),
           ("intake.frequency", it.get("frequency"), key["job"]["frequency"])]
    true_stubs = [(f"{key['first']} {key['last']}", key["job"], d) for d in key["job"]["pay_dates"]]
    if key["spouse_job"]:
        true_stubs.append((f"{key['spouse_name']} {key['last']}", key["spouse_job"], key["spouse_job"]["pay_dates"][0]))
    used = set()
    for who, job, d in true_stubs:
        got = None
        cands = [(i, s) for i, s in enumerate(fx.stubs) if i not in used and
                 (not isinstance(s.get("employee"), Value) or not s["employee"].value or same_name(s["employee"].value, who, 80))]
        # same pay date first; otherwise the next unread stub of that person (its date was misread)
        hit = next(((i, s) for i, s in cands if isinstance(s.get("pay_date"), Value) and s["pay_date"].value == d), None)
        if hit is None:
            hit = next(((i, s) for i, s in cands if not (isinstance(s.get("pay_date"), Value) and s["pay_date"].value
                                                     and s["pay_date"].value in {x[2] for x in true_stubs})), None)
        if hit:
            used.add(hit[0])
            got = hit[1]
        for k in ("employer", "pay_date", "gross", "cpp", "ei", "tax", "net"):
            truth = d if k == "pay_date" else job[k]
            out.append((f"stub.{k}", got.get(k) if got else None, truth))
    if key["children"]:
        out.append(("benefit.children", fx.benefit.get("children"), key["children"]))
    tl = {t["last4"].value: t for t in fx.tradelines}
    for d in key["debts"]:
        if not d["on_bureau"]:
            continue
        t = tl.get(d["last4"])
        out.append(("tradeline.last4", t["last4"] if t else None, d["last4"]))
        out.append(("tradeline.balance", t["balance"] if t else None, d["balance"]))
    if key["collection"]:
        L = fx.letters[0] if fx.letters else {}
        out.append(("letter.last4", L.get("last4"), key["collection"]["last4"]))
        out.append(("letter.balance", L.get("balance"), key["collection"]["balance"]))
    return out


def evaluate(rows: list[tuple]) -> dict:
    """rows: (manifest row, FileExtraction, FileResult). Returns the metrics the README reports."""
    fields = defaultdict(lambda: [0, 0])
    by_capture = defaultdict(lambda: [0, 0])
    accepted = accepted_wrong = routed = total = 0
    surplus_ok = derived_ok = n_files = 0
    derived = defaultdict(lambda: [0, 0])
    pages_ok = pages_n = 0
    tp = fn = fp = 0
    per_trap = defaultdict(lambda: [0, 0])
    clean_files = clean_flagged = 0
    review_fields = all_fields = 0
    seconds = []
    silent_wrong = 0
    for m, fx, res in rows:
        key = m["answer"]
        n_files += 1
        seconds.append(fx.seconds + fx.ocr.get("ocr_seconds", 0.0))
        for f, v, truth in _pairs(fx, res, key):
            got = v.value if isinstance(v, Value) else None
            ok = _eq(got, truth)
            fields[f][0] += ok
            fields[f][1] += 1
            by_capture[m["capture"]][0] += ok
            by_capture[m["capture"]][1] += 1
            total += 1
            conf = v.conf if isinstance(v, Value) else 0.0
            if got is not None and conf >= REVIEW_CONF:
                accepted += 1
                accepted_wrong += not ok
            else:
                routed += 1
        for i, pk in enumerate(fx.page_kinds):
            if i < len(m["pages"]):
                pages_ok += pk["kind"] == m["pages"][i]["kind"]
                pages_n += 1
        fig, s = res.figures, res.surplus or {}
        checks = {"debtor_monthly": key["debtor_monthly"], "spouse_monthly": key["spouse_monthly"],
                  "persons": key["persons"], "child_support": key["child_support_paid"],
                  "unsecured_total": key["unsecured_total"]}
        good = True
        for k, truth in checks.items():
            ok = _eq(fig.get(k), float(truth) if isinstance(truth, float) else truth)
            derived[k][0] += ok
            derived[k][1] += 1
            good &= ok
        pay_ok = _eq(s.get("line15_monthly_payment"), key["surplus"]["line15_monthly_payment"])
        surplus_ok += pay_ok
        derived_ok += good and pay_ok
        flagged = any(f["severity"] == "check" for f in res.findings) or bool(res.review_fields)
        silent_wrong += (not (good and pay_ok)) and not flagged
        planted = set(key["traps"])
        found = {f["code"] for f in res.findings if f["code"] in TRAP_CODES}
        tp += len(planted & found)
        fn += len(planted - found)
        fp += len(found - planted)
        for t in planted:
            per_trap[t][0] += t in found
            per_trap[t][1] += 1
        if not planted:
            clean_files += 1
            clean_flagged += bool(found)
        review_fields += len(res.review_fields)
        all_fields += res.n_fields
    seconds.sort()
    return {
        "files": n_files,
        "field_accuracy": round(sum(a for a, _ in fields.values()) / max(total, 1), 4),
        "fields_scored": total,
        "by_field": {k: round(a / n, 4) for k, (a, n) in sorted(fields.items())},
        "by_capture": {k: round(a / n, 4) for k, (a, n) in sorted(by_capture.items())},
        "auto_accepted_share": round(accepted / max(total, 1), 4),
        "auto_accepted_error_rate": round(accepted_wrong / max(accepted, 1), 5),
        "auto_accepted_wrong": accepted_wrong,
        "review_share": round(review_fields / max(all_fields, 1), 4),
        "page_type_accuracy": round(pages_ok / max(pages_n, 1), 4),
        "surplus_payment_exact": round(surplus_ok / max(n_files, 1), 4),
        "file_figures_all_exact": round(derived_ok / max(n_files, 1), 4),
        "files_wrong_and_not_flagged": silent_wrong,
        "derived": {k: round(a / n, 4) for k, (a, n) in derived.items()},
        "traps_planted": tp + fn,
        "traps_caught": tp,
        "trap_recall": round(tp / max(tp + fn, 1), 4),
        "trap_false_alarms": fp,
        "trap_precision": round(tp / max(tp + fp, 1), 4),
        "per_trap_recall": {k: round(a / n, 4) for k, (a, n) in sorted(per_trap.items())},
        "clean_files": clean_files,
        "clean_files_flagged": clean_flagged,
        "seconds_median": round(seconds[len(seconds) // 2], 2) if seconds else 0,
        "seconds_p95": round(seconds[int(len(seconds) * 0.95) - 1], 2) if seconds else 0,
    }
