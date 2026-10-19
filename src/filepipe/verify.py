"""Turn an extraction into verified figures, proof check findings and a Form 65 / Form 79 pre-fill.

The checks are the ones Directive 11R2 para 5(4) asks the trustee to make by hand: proof of income and proof of
non-discretionary payments. Each finding cites the pages it came from. Nothing here files anything; the
output is a pre-fill for a person to approve.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from filepipe.extract.base import FileExtraction, Value
from filepipe.extract.parse import days_between, same_person
from filepipe.rules.surplus import Member, compute, monthly_from_pay

STALE_DAYS = 45            # newest pay stub older than this at signing is not current proof of income
UNDERSTATED_SHARE = 0.90   # intake income below 90% of the pay stub figure
REVIEW_CONF = 0.80
INTAKE_EXPECTED = ["name", "postal", "marital", "persons", "employer", "frequency", "stated_income",
                   "spouse_stated", "stated_support", "child_care", "medical", "rent", "signed_date"]
STUB_EXPECTED = ["employer", "employee", "pay_date", "frequency", "gross", "cpp", "ei", "tax", "net"]

TRAP_CODES = ["intake_understated", "undeclared_income", "stale_stub", "missing_page",
              "family_size_mismatch", "duplicate_creditor", "support_not_declared"]


@dataclass
class Finding:
    code: str
    message: str
    pages: list
    severity: str = "check"  # check: a person must look; info: noted only


@dataclass
class FileResult:
    file_id: str
    extractor: str
    figures: dict
    findings: list
    review_fields: list
    n_fields: int
    surplus: dict | None
    creditors: list
    prefill: list = field(default_factory=list)


def _v(d: dict, k: str):
    x = d.get(k)
    return x.value if isinstance(x, Value) else None


def _page(d: dict, k: str):
    x = d.get(k)
    return x.cite.page if isinstance(x, Value) and x.cite else None


def _employer_in(desc: str, employer: str) -> bool:
    return fuzz.partial_ratio(employer.upper()[:28], desc.upper()) >= 85


def verify(fx: FileExtraction) -> FileResult:
    it = fx.intake
    findings: list[Finding] = []
    name = _v(it, "name") or ""
    stubs = [s for s in fx.stubs if _v(s, "net") is not None]
    mine = [s for s in stubs if not name or not _v(s, "employee") or same_person(_v(s, "employee"), name)]
    spouse = [s for s in stubs if s not in mine]
    mine.sort(key=lambda s: _v(s, "pay_date") or "", reverse=True)
    spouse.sort(key=lambda s: _v(s, "pay_date") or "", reverse=True)
    newest = mine[0] if mine else None
    freq = (_v(newest, "frequency") if newest else None) or _v(it, "frequency") or "monthly"

    main_monthly = monthly_from_pay(_v(newest, "net"), freq) if newest else 0.0
    employers = [_v(s, "employer") or "" for s in stubs]
    tx = fx.bank.get("tx", [])
    side = [t for t in tx if t["kind"] == "deposit" and employers and not any(e and _employer_in(t["desc"], e) for e in employers)]
    side_income = round(sum(t["amount"] for t in side), 2)
    support_tx = [t for t in tx if t["kind"] == "withdrawal" and ("SUPPORT" in t["desc"].upper() or "FRO" in t["desc"].upper())]
    support_bank = round(sum(t["amount"] for t in support_tx), 2)
    stated_support = _v(it, "stated_support") or 0.0
    child_support = support_bank if support_bank else stated_support
    spouse_monthly = monthly_from_pay(_v(spouse[0], "net"), _v(spouse[0], "frequency") or "monthly") if spouse else 0.0
    marital = (_v(it, "marital") or "").lower()
    has_spouse = bool(spouse) or "married" in marital or "common" in marital
    children = _v(fx.benefit, "children") or 0
    persons = 1 + int(has_spouse) + int(children)
    debtor_monthly = round(main_monthly + side_income, 2)

    # proof checks
    stated = _v(it, "stated_income")
    if newest and stated is not None and stated < UNDERSTATED_SHARE * main_monthly:
        findings.append(Finding("intake_understated",
                                f"Intake says {stated:,.2f} a month; the newest pay stub works out to {main_monthly:,.2f}",
                                [_page(it, "stated_income"), newest["page"]]))
    if side:
        findings.append(Finding("undeclared_income",
                                f"Bank shows payroll deposits of {side_income:,.2f} from an employer with no pay stub",
                                sorted({t['cite'].page for t in side})))
    signed = _v(it, "signed_date")
    if newest and signed and _v(newest, "pay_date"):
        age = days_between(_v(newest, "pay_date"), signed)
        if age > STALE_DAYS:
            findings.append(Finding("stale_stub", f"Newest pay stub is {age} days older than the signed intake",
                                    [newest["page"], _page(it, "signed_date")]))
    declared, seen = fx.bank.get("pages_declared", 0), set(fx.bank.get("pages_seen", []))
    bank_pages = sum(1 for p in fx.page_kinds if p["kind"] == "bank_statement")
    if declared and len(seen) < declared and bank_pages < declared:  # a page number can be misread; count pages too
        missing = sorted(set(range(1, declared + 1)) - seen)
        findings.append(Finding("missing_page", f"Bank statement says {declared} pages; page {', '.join(map(str, missing))} not in the packet",
                                [_page(fx.bank, "period")]))
    stated_persons = _v(it, "persons")
    if stated_persons is not None and stated_persons != persons:
        findings.append(Finding("family_size_mismatch",
                                f"Intake says {stated_persons} persons; documents show {persons}",
                                [_page(it, "persons"), _page(fx.benefit, "children")]))
    if support_bank and not stated_support:
        findings.append(Finding("support_not_declared",
                                f"Bank shows support payments of {support_bank:,.2f} that the intake does not list",
                                sorted({t['cite'].page for t in support_tx})))

    # creditors: a collector letter either duplicates a bureau line or adds a new debt
    creditors = [{"name": t["creditor"].value, "last4": t["last4"].value, "balance": t["balance"].value,
                  "source": "credit_report", "page": t["balance"].cite.page} for t in fx.tradelines]
    for L in fx.letters:
        l4, bal = _v(L, "last4"), _v(L, "balance")
        if l4 is None or bal is None:
            continue
        dup = next((c for c in creditors if c["last4"] == l4 and c["source"] == "credit_report"), None)
        if dup:
            findings.append(Finding("duplicate_creditor",
                                    f"Collector letter for account ending {l4} is the same debt as {dup['name']}; counted once",
                                    [dup["page"], _page(L, "balance")]))
        else:
            creditors.append({"name": _v(L, "original") or "", "last4": l4, "balance": bal,
                              "source": "collection_letter", "page": _page(L, "balance")})

    if not newest:
        findings.append(Finding("no_income_proof", "No readable pay stub for the client", []))
    if (_v(it, "spouse_stated") or 0) > 0 and not spouse:
        findings.append(Finding("spouse_income_unproven",
                                f"Intake lists spouse income of {_v(it, 'spouse_stated'):,.2f} a month but no spouse pay stub was read",
                                [_page(it, "spouse_stated")]))
    tot = fx.bank.get("credit_total")
    read_sum = round(sum(t["balance"].value for t in fx.tradelines), 2)
    if fx.tradelines and tot is not None and tot.value is not None and abs(read_sum - tot.value) > 0.02:
        findings.append(Finding("creditor_lines_unread",
                                f"Credit report total is {tot.value:,.2f} but the lines read add to {read_sum:,.2f}",
                                [tot.cite.page]))
        gap = round(tot.value - read_sum, 2)
        if gap > 0:  # carry the unread amount so the creditor total matches the report; a person names the line
            creditors.append({"name": "Unread credit report line", "last4": None, "balance": gap,
                              "source": "credit_report_total", "page": tot.cite.page})
    for k in ("child_care", "medical"):
        if (_v(it, k) or 0) > 0:
            findings.append(Finding(f"{k}_proof", f"{k.replace('_', ' ').title()} is client stated; collect a receipt",
                                    [_page(it, k)], severity="info"))

    nd = {k: v for k, v in {"child_support": child_support, "child_care": _v(it, "child_care") or 0.0,
                            "medical": _v(it, "medical") or 0.0}.items() if v}
    surplus = compute(Member(debtor_monthly, nd), [Member(spouse_monthly)] if spouse else [], persons=persons).as_dict() if newest else None

    # every field read, and the ones a person should look at
    all_vals = []
    for d in [it, fx.benefit] + fx.stubs + fx.letters:
        all_vals += [(k, v) for k, v in d.items() if isinstance(v, Value)]
    for t in fx.tradelines:
        all_vals += [("tradeline." + k, t[k]) for k in ("last4", "balance")]
    review = [{"field": k, "value": v.value, "page": v.cite.page if v.cite else None, "conf": round(v.conf, 3)}
              for k, v in all_vals if v.value is None or v.conf < REVIEW_CONF]
    # a field that should be on the page but was not read at all also goes to a person
    gaps = [("intake." + k, it) for k in INTAKE_EXPECTED if k not in it]
    for s_ in fx.stubs:
        gaps += [("stub." + k, s_) for k in STUB_EXPECTED if k not in s_]
    for k, _ in gaps:
        review.append({"field": k, "value": None, "page": None, "conf": 0.0})

    figures = {"debtor_monthly": debtor_monthly, "main_job_monthly": main_monthly, "side_income": side_income,
               "spouse_monthly": spouse_monthly, "child_support": child_support, "persons": persons,
               "unsecured_total": round(sum(c["balance"] for c in creditors), 2), "frequency": freq,
               "stated_income": stated, "postal": _v(it, "postal"), "name": name}
    res = FileResult(fx.file_id, fx.extractor, figures, [f.__dict__ for f in findings], review, len(all_vals) + len(gaps),
                     surplus, creditors)
    res.prefill = prefill_rows(res, fx)
    return res


def prefill_rows(r: FileResult, fx: FileExtraction) -> list[dict]:
    """Rows for an Ascend quick entry or Dataverse import: field, value, source page. Pre-fill only."""
    s = r.surplus or {}
    rows = [
        ("form65.line1_debtor_net_income", s.get("line1_debtor_net_income"), "pay stub and bank deposits"),
        ("form65.line2_other_members_net_income", s.get("line2_other_members_net_income"), "spouse pay stub"),
        ("form65.line4_debtor_non_discretionary", s.get("line4_debtor_non_discretionary"), "bank statement / intake"),
        ("form65.line8_family_available", s.get("line8_family_available"), "computed"),
        ("form65.line9_debtor_share_pct", s.get("line9_debtor_share_pct"), "computed"),
        ("form65.persons", r.figures["persons"], "intake, benefit statement, pay stubs"),
        ("form65.standard", s.get("standard"), "Directive 11R2-2026 Appendix A"),
        ("form65.line15_monthly_payment", s.get("line15_monthly_payment"), "computed"),
        ("form79.unsecured_total", r.figures["unsecured_total"], "credit report and collector letters"),
    ]
    out = [{"file_id": r.file_id, "field": f, "value": v, "source": src} for f, v, src in rows]
    for c in r.creditors:
        out.append({"file_id": r.file_id, "field": "form79.creditor", "value": f"{c['name']} | {c['last4']} | {c['balance']:.2f}",
                    "source": f"{c['source']} page {c['page']}"})
    return out
