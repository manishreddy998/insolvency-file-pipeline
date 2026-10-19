"""Draw a household's documents as a single PDF packet, the way a client might email or fax them in.

Layouts vary on purpose (labels, order, date formats) so the reader cannot lean on one template.
Every page carries a synthetic data footer.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from filepipe.rules.surplus import PERIODS_PER_YEAR
from filepipe.synth.households import Household

W, H = letter
FOOTER = "SYNTHETIC TEST DOCUMENT. Not a real person, employer or account."


def money(x: float, rng: random.Random | None = None, sign: bool = True) -> str:
    s = f"{x:,.2f}"
    return f"${s}" if sign else s


def fmt_date(iso: str, style: int) -> str:
    d = date.fromisoformat(iso)
    return [d.isoformat(), d.strftime("%b %d, %Y"), d.strftime("%d/%m/%Y"), d.strftime("%B %d, %Y")][style]


class Page:
    def __init__(self, kind: str, doc: str):
        self.kind, self.doc, self.ops = kind, doc, []

    def title(self, t): self.ops.append(("title", t))
    def sub(self, t): self.ops.append(("sub", t))
    def kv(self, k, v): self.ops.append(("kv", k, str(v)))
    def text(self, t): self.ops.append(("text", t))
    def gap(self): self.ops.append(("gap",))
    def table(self, cols, rows, xs): self.ops.append(("table", cols, rows, xs))


def _intake(h: Household, rng: random.Random) -> list[Page]:
    p = Page("intake", "intake")
    p.title("Debt Assessment Intake Worksheet")
    p.sub("Completed by the client before the first meeting")
    p.gap()
    p.kv("Client name", f"{h.first} {h.last}")
    p.kv("Street address", h.street)
    p.kv("City / Province", f"{h.city}, {h.province}")
    p.kv("Postal code", h.postal)
    p.kv("Marital status", "Married or common law" if h.spouse else rng.choice(["Single", "Separated", "Divorced"]))
    p.kv("Persons in household (including you)", h.stated_persons)
    p.gap()
    p.kv("Employer", h.job.employer)
    p.kv("Pay frequency", {"biweekly": "Every two weeks", "semimonthly": "Twice a month",
                           "weekly": "Weekly", "monthly": "Monthly"}[h.job.frequency])
    p.kv("Your monthly take home pay", money(h.stated_income))
    p.kv("Spouse or partner monthly take home pay", money(h.spouse_monthly) if h.spouse_job else "None")
    p.gap()
    p.kv("Child support you pay each month", money(h.stated_support) if h.stated_support else "None")
    p.kv("Child care each month", money(h.child_care) if h.child_care else "None")
    p.kv("Medical costs each month", money(h.medical) if h.medical else "None")
    p.kv("Rent or mortgage each month", money(h.rent))
    p.gap()
    p.text("I confirm the information above is true to the best of my knowledge.")
    p.text(f"Signed: {h.first} {h.last}      Date: {fmt_date(h.packet_date, 1)}")
    return [p]


STUB_LAYOUTS = [
    dict(title="EARNINGS STATEMENT", emp="Employer", date="Pay Date", gross="Gross Pay", cpp="CPP",
         ei="EI", tax="Income Tax", net="Net Pay", period="Pay Period"),
    dict(title="Pay Statement", emp="Company", date="Cheque Date", gross="Total Earnings", cpp="CPP Contribution",
         ei="EI Premium", tax="Federal/Provincial Tax", net="Net Amount", period="Period"),
    dict(title="PAYSLIP", emp="Paid by", date="Payment Date", gross="Gross Earnings", cpp="Canada Pension Plan",
         ei="Employment Insurance", tax="Tax Deducted", net="Take Home Pay", period="Frequency"),
]


def _stub(name: str, job, iso: str, rng: random.Random, layout: int, ds: int) -> Page:
    L = STUB_LAYOUTS[layout]
    p = Page("pay_stub", "pay_stub")
    p.title(L["title"])
    p.kv(L["emp"], job.employer)
    p.kv("Employee", name)
    p.kv(L["date"], fmt_date(iso, ds))
    p.kv(L["period"], {"biweekly": "Bi-weekly", "semimonthly": "Semi-monthly", "weekly": "Weekly",
                       "monthly": "Monthly"}[job.frequency])
    p.gap()
    hours = {"weekly": 37.5, "biweekly": 75, "semimonthly": 81.25, "monthly": 162.5}[job.frequency]
    p.kv("Regular hours", f"{hours:.2f}")
    p.kv(L["gross"], money(job.gross))
    p.gap()
    p.sub("Deductions")
    p.kv(L["cpp"], money(job.cpp))
    p.kv(L["ei"], money(job.ei))
    p.kv(L["tax"], money(job.tax))
    p.gap()
    p.kv(L["net"], money(job.net))
    n = PERIODS_PER_YEAR[job.frequency]
    d = date.fromisoformat(iso)
    ytd_periods = max(1, round((d - date(d.year, 1, 1)).days / (365 / n)))
    p.kv("Year to date gross", money(job.gross * ytd_periods))
    return p


def _bank(h: Household, rng: random.Random, layout: int, ds: int) -> list[Page]:
    end = date.fromisoformat(h.packet_date) - timedelta(days=rng.randint(1, 6))
    start = end - timedelta(days=30)
    tx = []  # (date, description, withdrawal, deposit)
    step = {"weekly": 7, "biweekly": 14, "semimonthly": 15, "monthly": 30}[h.job.frequency]
    d = start + timedelta(days=rng.randint(0, step - 1))
    while d <= end:
        tx.append((d, f"PAYROLL DEP {h.job.employer.upper()[:28]}", 0.0, h.job.net))
        d += timedelta(days=step)
    if h.side_income:
        tx.append((start + timedelta(days=rng.randint(3, 27)), f"PAYROLL DEP {h.side_employer.upper()[:28]}", 0.0, h.side_income))
    tx.append((start + timedelta(days=rng.randint(0, 4)), "E-TFR RENT PAYMENT", h.rent, 0.0))
    if h.child_support_paid:
        tx.append((start + timedelta(days=rng.randint(5, 20)), "FRO SUPPORT PMT", h.child_support_paid, 0.0))
    misc = ["GROCERY STORE", "GAS STATION", "PHARMACY", "TRANSIT PASS", "PHONE BILL", "HYDRO BILL", "COFFEE SHOP",
            "HARDWARE STORE", "ONLINE ORDER", "RESTAURANT"]
    for _ in range(rng.randint(10, 20)):
        tx.append((start + timedelta(days=rng.randint(0, 30)), rng.choice(misc), round(rng.uniform(8, 240), 2), 0.0))
    tx.sort(key=lambda t: t[0])
    key_rows = [t for t in tx if t[3] or "RENT" in t[1] or "FRO" in t[1]]
    other = [t for t in tx if t not in key_rows]
    two_pages = "missing_page" in h.traps or rng.random() < 0.35
    first_rows = sorted(key_rows + (other[: len(other) // 2] if two_pages else other), key=lambda t: t[0])
    second_rows = other[len(other) // 2:] if two_pages else []
    n_pages = 2 if two_pages else 1
    bank = rng.choice(["Lakeshore Bank", "Granite Bay Bank", "Harbourline Credit Union"])
    acct = f"****{rng.randint(1000, 9999)}"
    pages = []
    for i, rows in enumerate([first_rows, second_rows][:n_pages]):
        p = Page("bank_statement", "bank_statement")
        p.title(f"{bank} Chequing Account Statement" if layout == 0 else f"{bank.upper()} STATEMENT OF ACCOUNT")
        p.kv("Account holder", f"{h.first} {h.last}")
        p.kv("Account", acct)
        p.kv("Statement period", f"{fmt_date(start.isoformat(), ds)} to {fmt_date(end.isoformat(), ds)}")
        p.kv("Page", f"{i + 1} of {n_pages}")
        p.gap()
        p.table(["Date", "Description", "Withdrawals", "Deposits"],
                [[fmt_date(t[0].isoformat(), 0), t[1], money(t[2], sign=False) if t[2] else "",
                  money(t[3], sign=False) if t[3] else ""] for t in rows], [50, 130, 400, 500])
        pages.append(p)
    if "missing_page" in h.traps:
        pages = pages[:1]  # the client sent page 1 of 2 only
    return pages


def _benefit(h: Household, rng: random.Random, ds: int) -> Page:
    p = Page("benefit_statement", "benefit_statement")
    p.title("Child Benefit Statement")
    p.sub("Benefit year July 2026 to June 2027")
    p.kv("Recipient", f"{h.first} {h.last}" if rng.random() < 0.6 or not h.spouse else f"{h.spouse_name} {h.last}")
    p.kv("Number of eligible children", h.children)
    p.kv("Monthly benefit", money(h.children * rng.uniform(280, 640)))
    p.kv("Date issued", fmt_date("2026-07-20", ds))
    return p


def _credit(h: Household, rng: random.Random) -> Page:
    p = Page("credit_report", "credit_report")
    p.title("Consumer Credit Report: Summary of Accounts")
    p.kv("Consumer", f"{h.last.upper()}, {h.first.upper()}")
    p.kv("Report date", fmt_date(h.packet_date, 0))
    p.gap()
    rows = [[d.lender, d.kind, f"xxxx{d.last4}", money(d.balance, sign=False), rng.choice(["Past due", "Charged off", "Current", "Collection"])]
            for d in h.debts if d.on_bureau]
    p.table(["Creditor", "Type", "Account", "Balance", "Status"], rows, [40, 220, 330, 420, 500])
    p.gap()
    p.kv("Total balance", money(sum(d.balance for d in h.debts if d.on_bureau)))
    return p


def _collection(h: Household, rng: random.Random, ds: int) -> Page:
    c = h.collection
    p = Page("collection_letter", "collection_letter")
    p.title(c["agency"])
    p.sub("Notice of debt in collection")
    p.kv("To", f"{h.first} {h.last}")
    p.kv("Date", fmt_date((date.fromisoformat(h.packet_date) - timedelta(days=rng.randint(5, 40))).isoformat(), ds))
    p.kv("Original creditor", c["original"])
    p.kv("Account ending", c["last4"])
    p.kv("Amount owing", money(c["balance"]))
    p.gap()
    p.text("Our records show the above account is past due. Please contact our office to arrange payment.")
    return p


def build_pages(h: Household, rng: random.Random) -> list[Page]:
    ds = rng.randint(0, 3)
    docs = [_intake(h, rng)]
    lay = rng.randint(0, 2)
    name = f"{h.first} {h.last}"
    docs.append([_stub(name, h.job, d, rng, lay, ds) for d in h.job.pay_dates])
    if h.spouse_job:
        docs.append([_stub(f"{h.spouse_name} {h.last}", h.spouse_job, h.spouse_job.pay_dates[0], rng, rng.randint(0, 2), ds)])
    docs.append(_bank(h, rng, rng.randint(0, 1), ds))
    if h.children:
        docs.append([_benefit(h, rng, ds)])
    docs.append([_credit(h, rng)])
    if h.collection:
        docs.append([_collection(h, rng, ds)])
    first, rest = docs[0], docs[1:]
    rng.shuffle(rest)  # clients rarely send documents in order; the intake usually comes first
    return [p for d in [first] + rest for p in d]


def draw_pdf(pages: list[Page], path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Synthetic client packet")
    for p in pages:
        y = H - 60
        for op in p.ops:
            if op[0] == "title":
                c.setFont("Helvetica-Bold", 16); c.drawString(50, y, op[1]); y -= 26
            elif op[0] == "sub":
                c.setFont("Helvetica-Oblique", 11); c.drawString(50, y, op[1]); y -= 20
            elif op[0] == "kv":
                c.setFont("Helvetica-Bold", 11); c.drawString(50, y, op[1] + ":")
                c.setFont("Helvetica", 11); c.drawString(300, y, op[2]); y -= 19
            elif op[0] == "text":
                c.setFont("Helvetica", 11); c.drawString(50, y, op[1]); y -= 19
            elif op[0] == "gap":
                y -= 10
            elif op[0] == "table":
                _, cols, rows, xs = op
                c.setFont("Helvetica-Bold", 10)
                for x, col in zip(xs, cols):
                    c.drawString(x, y, col)
                y -= 16
                c.setFont("Helvetica", 10)
                for r in rows:
                    for x, v in zip(xs, r):
                        c.drawString(x, y, str(v))
                    y -= 15
                    if y < 70:
                        break
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(50, 30, FOOTER)
        c.showPage()
    c.save()
