"""Local readers that turn OCR lines into fields with a page citation.

labels-v1          exact labels and clean amounts only. The simple starting point.
layout-v2          fuzzy labels, OCR digit repair, pay stub arithmetic and cross document checks.
layout-v2-fastocr  the same reader on the cheap OCR setup (scored with a separate OCR pass).
"""
from __future__ import annotations

import re
import time

from rapidfuzz import fuzz

from .base import Cite, Extractor, FileExtraction, Value, register
from .parse import parse_date, parse_int, parse_money, parse_postal, same_name

KINDS = {
    "intake": ["debt assessment intake worksheet", "completed by the client"],
    "pay_stub": ["earnings statement", "pay statement", "payslip", "net pay", "take home pay", "net amount"],
    "bank_statement": ["chequing account statement", "statement of account", "statement period"],
    "benefit_statement": ["child benefit statement", "number of eligible children"],
    "credit_report": ["consumer credit report", "summary of accounts"],
    "collection_letter": ["notice of debt in collection", "original creditor"],
}

LABELS = {
    "intake": {
        "client name": "name", "postal code": "postal", "marital status": "marital",
        "persons in household (including you)": "persons", "employer": "employer", "pay frequency": "frequency",
        "your monthly take home pay": "stated_income", "spouse or partner monthly take home pay": "spouse_stated",
        "child support you pay each month": "stated_support", "child care each month": "child_care",
        "medical costs each month": "medical", "rent or mortgage each month": "rent",
    },
    "pay_stub": {
        "employer": "employer", "company": "employer", "paid by": "employer", "employee": "employee",
        "pay date": "pay_date", "cheque date": "pay_date", "payment date": "pay_date",
        "pay period": "frequency", "period": "frequency", "frequency": "frequency",
        "gross pay": "gross", "total earnings": "gross", "gross earnings": "gross",
        "cpp": "cpp", "cpp contribution": "cpp", "canada pension plan": "cpp",
        "ei": "ei", "ei premium": "ei", "employment insurance": "ei",
        "income tax": "tax", "federal/provincial tax": "tax", "tax deducted": "tax",
        "net pay": "net", "net amount": "net", "take home pay": "net",
        "regular hours": "hours", "year to date gross": "ytd",
    },
    "bank_statement": {"account holder": "holder", "account": "account", "statement period": "period", "page": "page"},
    "benefit_statement": {"recipient": "recipient", "number of eligible children": "children"},
    "credit_report": {"consumer": "consumer", "report date": "report_date", "total balance": "total"},
    "collection_letter": {"to": "to", "date": "date", "original creditor": "original",
                          "account ending": "last4", "amount owing": "balance"},
}
MONEY_FIELDS = {"stated_income", "spouse_stated", "stated_support", "child_care", "medical", "rent",
                "gross", "cpp", "ei", "tax", "net", "ytd", "total", "balance"}
FREQ_WORDS = {"every two weeks": "biweekly", "bi-weekly": "biweekly", "biweekly": "biweekly",
              "twice a month": "semimonthly", "semi-monthly": "semimonthly", "weekly": "weekly", "monthly": "monthly"}
DEBT_KINDS = ["credit card", "line of credit", "instalment loan", "payday loan", "retail card", "auto deficiency",
              "income tax", "utility"]
TX_DATE = re.compile(r"^\W{0,2}(20[0-9OoIl]{2}[-./][0-9OoIl]{2}[-./][0-9OoIl]{2})")
LAST4 = re.compile(r"[xX%*]{3,5}\s?([0-9OoIlSB]{4})\b")


def _freq(text: str, fuzzy: bool) -> str | None:
    t = text.lower().strip()
    for k, v in sorted(FREQ_WORDS.items(), key=lambda kv: -len(kv[0])):
        if k in t:
            return v
    if fuzzy:
        best = max(FREQ_WORDS, key=lambda k: fuzz.ratio(k, t))
        if fuzz.ratio(best, t) >= 80:
            return FREQ_WORDS[best]
    return None


def _digits(s: str) -> str:
    return s.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"}))


class LabelReader(Extractor):
    name = "labels-v1"
    fuzzy = False
    validate = False

    # page types
    def classify(self, lines) -> tuple[str, float]:
        head = " ".join(l.text.lower() for l in lines[:10])
        best, score = "unknown", 0.0
        for kind, keys in KINDS.items():
            for k in keys:
                s = 100.0 if k in head else (fuzz.partial_ratio(k, head) if self.fuzzy else 0.0)
                if s > score:
                    best, score = kind, s
        return (best, score / 100) if score >= 85 else ("unknown", score / 100)

    # label: value lines
    def split(self, text: str, kind: str):
        labels = LABELS[kind]
        if ":" in text:
            k, v = text.split(":", 1)
            k = k.strip().lower()
            if k in labels:
                return labels[k], v.strip()
            if self.fuzzy:
                best = max(labels, key=lambda lab: fuzz.ratio(lab, k))
                if fuzz.ratio(best, k) >= 82:
                    return labels[best], v.strip()
            return None
        if self.fuzzy:  # the colon was lost in OCR: match the leading words
            words = text.split()
            best, score, cut = None, 0, 0
            for lab in labels:
                n = len(lab.split())
                if len(words) <= n:
                    continue
                s = fuzz.ratio(lab, " ".join(words[:n]).lower())
                if s > score:
                    best, score, cut = lab, s, n
            if best and score >= 86:
                return labels[best], " ".join(words[cut:])
        return None

    def _value(self, fieldname: str, raw: str):
        if fieldname in MONEY_FIELDS:
            if raw.strip().lower() in ("none", "nil", "n/a"):
                return 0.0
            return parse_money(raw, repair=self.fuzzy)
        if fieldname in ("persons", "children"):
            return parse_int(raw)
        if fieldname == "frequency":
            return _freq(raw, self.fuzzy)
        if fieldname in ("pay_date", "report_date", "date"):
            return parse_date(raw)
        if fieldname == "postal":
            return parse_postal(raw) if self.fuzzy else (raw.strip().upper() if re.fullmatch(r"[A-Z]\d[A-Z] \d[A-Z]\d", raw.strip().upper()) else None)
        if fieldname == "last4":
            m = re.search(r"([0-9OoIlSB]{4})", raw)
            return (_digits(m.group(1)) if self.fuzzy else m.group(1)) if m else None
        return raw.strip()

    def kv(self, lines, kind: str) -> dict:
        out = {}
        for ln in lines:
            hit = self.split(ln.text, kind)
            if not hit:
                continue
            f, raw = hit
            if f in out and out[f].value is not None:
                continue
            v = self._value(f, raw)
            if v is None and f in out:
                continue
            out[f] = Value(v, Cite(ln.page + 1, ln.text, ln.conf / 100))
        return out

    # documents
    def intake(self, lines, fx: FileExtraction):
        d = self.kv(lines, "intake")
        for ln in lines:
            if ln.text.lower().startswith("signed") or "date:" in ln.text.lower():
                dt = parse_date(ln.text.split("Date")[-1] if "Date" in ln.text else ln.text)
                if dt:
                    d["signed_date"] = Value(dt, Cite(ln.page + 1, ln.text, ln.conf / 100))
        fx.intake.update({k: v for k, v in d.items() if k not in fx.intake})

    def stub(self, lines, fx: FileExtraction):
        d = self.kv(lines, "pay_stub")
        d["page"] = lines[0].page + 1 if lines else 0
        fx.stubs.append(d)

    def bank(self, lines, fx: FileExtraction):
        d = self.kv(lines, "bank_statement")
        b = fx.bank
        for k in ("holder", "account", "period"):
            if k in d and k not in b:
                b[k] = d[k]
        pg = d.get("page")
        if pg and pg.value:
            m = re.search(r"([0-9OIl]+)\s*(?:of|0f|/)\s*([0-9OIl]+)", pg.value)
            if m and _digits(m.group(1)).isdigit() and _digits(m.group(2)).isdigit():
                b.setdefault("pages_seen", []).append(int(_digits(m.group(1))))
                b["pages_declared"] = max(b.get("pages_declared", 0), int(_digits(m.group(2))))
        for ln in lines:
            m = TX_DATE.match(ln.text)
            if not m:
                continue
            amt = parse_money(ln.text[m.end():], repair=self.fuzzy)
            if amt is None:
                continue
            desc = ln.text[m.end():].strip()
            desc = re.sub(r"\s*\$?[0-9OoSslI|,.\s]+$", "", desc).strip()
            dl = desc.lower()
            kind = "deposit" if ("payroll" in dl or (self.fuzzy and fuzz.partial_ratio("payroll dep", dl) >= 85)) else "withdrawal"
            b.setdefault("tx", []).append({"desc": desc, "amount": amt, "kind": kind,
                                           "cite": Cite(ln.page + 1, ln.text, ln.conf / 100)})

    def benefit(self, lines, fx: FileExtraction):
        fx.benefit.update(self.kv(lines, "benefit_statement"))

    def credit(self, lines, fx: FileExtraction):
        d = self.kv(lines, "credit_report")
        if "total" in d:
            fx.bank.setdefault("credit_total", d["total"])
        for ln in lines:
            m = LAST4.search(ln.text)
            if not m:
                continue
            bal = parse_money(ln.text[m.end():], repair=self.fuzzy)
            if bal is None:
                continue
            before = ln.text[:m.start()].strip()
            kind = None
            for k in DEBT_KINDS:
                i = before.lower().rfind(k)
                if i >= 0:
                    kind, before = k, before[:i].strip()
                    break
            last4 = _digits(m.group(1)) if self.fuzzy else m.group(1)
            if not last4.isdigit():
                continue
            fx.tradelines.append({"creditor": Value(before, Cite(ln.page + 1, ln.text, ln.conf / 100)),
                                  "kind": kind, "last4": Value(last4, Cite(ln.page + 1, ln.text, ln.conf / 100)),
                                  "balance": Value(bal, Cite(ln.page + 1, ln.text, ln.conf / 100))})

    def letter(self, lines, fx: FileExtraction):
        d = self.kv(lines, "collection_letter")
        if lines:
            d["agency"] = Value(lines[0].text.strip(), Cite(lines[0].page + 1, lines[0].text, lines[0].conf / 100))
        fx.letters.append(d)

    def check(self, fx: FileExtraction) -> None:
        """Cross checks. The simple reader trusts what it read."""

    def extract(self, file_id: str, packet) -> FileExtraction:
        t0 = time.perf_counter()
        fx = FileExtraction(file_id, self.name, ocr={k: v for k, v in packet.features.items() if k != "page_confs"})
        handlers = {"intake": self.intake, "pay_stub": self.stub, "bank_statement": self.bank,
                    "benefit_statement": self.benefit, "credit_report": self.credit, "collection_letter": self.letter}
        for p in range(packet.n_pages):
            lines = packet.page_lines(p)
            kind, conf = self.classify(lines)
            fx.page_kinds.append({"page": p + 1, "kind": kind, "conf": round(conf, 3)})
            if kind in handlers:
                handlers[kind](lines, fx)
        self.check(fx)
        fx.seconds = time.perf_counter() - t0
        return fx


@register
class LabelsV1(LabelReader):
    name = "labels-v1"


@register
class LayoutV2(LabelReader):
    name = "layout-v2"
    fuzzy = True
    validate = True

    def check(self, fx: FileExtraction) -> None:
        deposits = [t for t in fx.bank.get("tx", []) if t["kind"] == "deposit"]
        for s in fx.stubs:
            vals = {k: s[k].value for k in ("gross", "cpp", "ei", "tax", "net") if k in s and s[k].value is not None}
            if len(vals) == 5:
                ok = abs(vals["gross"] - vals["cpp"] - vals["ei"] - vals["tax"] - vals["net"]) < 0.02
                if ok:
                    for k in vals:
                        s[k].validated = True
                else:
                    # one misread amount: rebuild net from the other four and send it to review
                    rebuilt = round(vals["gross"] - vals["cpp"] - vals["ei"] - vals["tax"], 2)
                    if any(abs(t["amount"] - rebuilt) < 0.01 for t in deposits):
                        s["net"].value, s["net"].validated = rebuilt, True
                        for k in ("gross", "cpp", "ei", "tax"):
                            s[k].validated = True
                    else:
                        for k in vals:
                            s[k].cite.conf = min(s[k].cite.conf, 0.6)
            if "net" in s and s["net"].value is not None and any(abs(t["amount"] - s["net"].value) < 0.01 for t in deposits):
                s["net"].validated = True
        tl = fx.tradelines
        tot = fx.bank.get("credit_total")
        if tl and tot is not None and tot.value is not None and abs(sum(t["balance"].value for t in tl) - tot.value) < 0.02:
            for t in tl:
                t["balance"].validated = t["last4"].validated = True
        # the intake employer should match a stub employer
        emp = fx.intake.get("employer")
        if emp and emp.value:
            for s in fx.stubs:
                if "employer" in s and s["employer"].value and same_name(emp.value, s["employer"].value, 88):
                    emp.validated = s["employer"].validated = True
                    if emp.value != s["employer"].value and s["employer"].cite.conf > emp.cite.conf:
                        emp.value = s["employer"].value


@register
class LayoutV2FastOcr(LayoutV2):
    name = "layout-v2-fastocr"
    ocr = "fast"
