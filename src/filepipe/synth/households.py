"""Synthetic households that come to a trustee with debt. Every person, employer and lender is made up.

Each household carries an answer key: the true values a careful trustee would land on after checking the
documents against each other, and the list of traps planted in its packet.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from faker import Faker

from filepipe.rules.surplus import Member, compute, monthly_from_pay

LENDERS = [  # fictional names only
    ("Lakeshore Bank Visa", "credit card"), ("Prairie Trust Mastercard", "credit card"),
    ("Harbourline Credit Union", "line of credit"), ("Northfield Financial", "instalment loan"),
    ("Maple Ridge Bank", "line of credit"), ("QuickFunds Payday", "payday loan"),
    ("Cedar Point Retail Card", "retail card"), ("Summit Auto Credit", "auto deficiency"),
    ("Granite Bay Bank Visa", "credit card"), ("Riverbend Lending", "instalment loan"),
    ("Canada Revenue Agency", "income tax"), ("Bluewater Telecom", "utility"),
]
# how a collector or a bureau may print the same lender under another name
ALIASES = {
    "Lakeshore Bank Visa": "LSB CARD SERVICES", "Prairie Trust Mastercard": "PT FINANCIAL MC",
    "Harbourline Credit Union": "HARBOURLINE CU", "Northfield Financial": "NFLD FIN SVCS",
    "Maple Ridge Bank": "MRB LENDING", "QuickFunds Payday": "QF LOANS INC",
    "Cedar Point Retail Card": "CPR CARD", "Summit Auto Credit": "SAC RECOVERY",
    "Granite Bay Bank Visa": "GBB VISA", "Riverbend Lending": "RBL CREDIT",
    "Canada Revenue Agency": "CRA COLLECTIONS", "Bluewater Telecom": "BW TELECOM",
}
AGENCIES = ["Allied Recovery Partners", "Northern Collection Bureau", "Keystone Credit Services"]
FREQS = ["biweekly", "semimonthly", "weekly", "monthly"]
PROVINCES = [("ON", 0.62), ("BC", 0.13), ("AB", 0.13), ("MB", 0.04), ("SK", 0.03), ("NS", 0.03), ("NB", 0.02)]
TRAPS = ["intake_understated", "undeclared_income", "stale_stub", "missing_page",
         "family_size_mismatch", "duplicate_creditor", "support_not_declared"]


@dataclass
class Job:
    employer: str
    frequency: str
    gross: float
    cpp: float
    ei: float
    tax: float
    net: float
    pay_dates: list  # iso dates of the stubs in the packet, newest first


@dataclass
class Debt:
    lender: str
    kind: str
    last4: str
    balance: float
    on_bureau: bool = True  # False when the debt only shows up in a collector's letter


@dataclass
class Household:
    file_id: str
    packet_date: str
    first: str
    last: str
    street: str
    city: str
    province: str
    postal: str
    spouse: bool
    spouse_name: str
    children: int
    job: Job
    spouse_job: Job | None
    side_income: float  # monthly deposits from a second employer, 0 if none
    side_employer: str
    child_support_paid: float
    child_care: float
    medical: float
    rent: float
    debts: list
    collection: dict | None  # a collector letter for one of the debts
    traps: list = field(default_factory=list)
    stated_income: float = 0.0
    stated_persons: int = 1
    stated_support: float = 0.0

    @property
    def persons(self) -> int:
        return 1 + int(self.spouse) + self.children

    @property
    def debtor_monthly(self) -> float:
        return round(monthly_from_pay(self.job.net, self.job.frequency) + self.side_income, 2)

    @property
    def spouse_monthly(self) -> float:
        return monthly_from_pay(self.spouse_job.net, self.spouse_job.frequency) if self.spouse_job else 0.0

    def surplus(self) -> dict:
        nd = {k: v for k, v in {"child_support": self.child_support_paid, "child_care": self.child_care,
                                "medical": self.medical}.items() if v}
        others = [Member(self.spouse_monthly)] if self.spouse_job else []
        return compute(Member(self.debtor_monthly, nd), others, persons=self.persons).as_dict()

    def unsecured_total(self) -> float:
        return round(sum(d.balance for d in self.debts), 2)

    def answer_key(self) -> dict:
        k = asdict(self)
        k["persons"] = self.persons
        k["debtor_monthly"] = self.debtor_monthly
        k["spouse_monthly"] = self.spouse_monthly
        k["unsecured_total"] = self.unsecured_total()
        k["surplus"] = self.surplus()
        return k


def _round(x: float) -> float:
    return round(x, 2)


def _job(fk: Faker, rng: random.Random, packet: date, annual: float, stale: bool) -> Job:
    freq = rng.choices(FREQS, [0.5, 0.25, 0.15, 0.10])[0]
    periods = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}[freq]
    gross = _round(annual / periods)
    cpp = _round(gross * 0.0595)
    ei = _round(gross * 0.0164)
    rate = 0.12 if annual < 45000 else 0.17 if annual < 75000 else 0.22
    tax = _round(gross * rate + rng.uniform(-8, 8))
    net = _round(gross - cpp - ei - tax)
    step = {"weekly": 7, "biweekly": 14, "semimonthly": 15, "monthly": 30}[freq]
    last = packet - timedelta(days=rng.randint(2, 12) + (rng.randint(75, 120) if stale else 0))
    dates = [last.isoformat(), (last - timedelta(days=step)).isoformat()]
    return Job(fk.company(), freq, gross, cpp, ei, tax, net, dates)


def picks_names(debts) -> set:
    return {d.lender for d in debts}


def make_household(i: int, rng: random.Random, fk: Faker, trap_rate: float = 0.55) -> Household:
    packet = date(2026, 9, 1) + timedelta(days=rng.randint(0, 44))
    prov = rng.choices([p for p, _ in PROVINCES], [w for _, w in PROVINCES])[0]
    traps = []
    if rng.random() < trap_rate:
        traps = rng.sample(TRAPS, k=rng.choices([1, 2], [0.75, 0.25])[0])
    spouse = rng.random() < 0.38
    children = rng.choices([0, 1, 2, 3], [0.45, 0.25, 0.2, 0.1])[0]
    annual = rng.choices([rng.uniform(28000, 48000), rng.uniform(48000, 72000), rng.uniform(72000, 105000)], [0.45, 0.35, 0.2])[0]
    job = _job(fk, rng, packet, annual, "stale_stub" in traps)
    spouse_job = _job(fk, rng, packet, rng.uniform(28000, 70000), False) if spouse and rng.random() < 0.7 else None
    side = _round(rng.uniform(450, 1400)) if "undeclared_income" in traps else 0.0
    support = _round(rng.uniform(250, 900)) if (rng.random() < 0.12 or "support_not_declared" in traps) else 0.0
    care = _round(rng.uniform(300, 1100)) if children and rng.random() < 0.4 else 0.0
    medical = _round(rng.uniform(40, 260)) if rng.random() < 0.12 else 0.0
    n_debts = rng.randint(3, 8)
    picks = rng.sample(LENDERS, n_debts)
    debts = [Debt(name, kind, f"{rng.randint(0, 9999):04d}",
                  _round(rng.uniform(800, 18000) if kind != "income tax" else rng.uniform(2000, 30000)))
             for name, kind in picks]
    collection = None
    if "duplicate_creditor" in traps:
        # a collector chases a debt that is already on the credit report, under another name
        d = rng.choice(debts)
        collection = {"agency": rng.choice(AGENCIES), "original": ALIASES[d.lender], "last4": d.last4,
                      "balance": _round(d.balance + rng.uniform(0, 120)), "duplicate": True}
    elif rng.random() < 0.3:
        # a debt the bureau never saw: it must be added to the creditor list
        name, kind = rng.choice([x for x in LENDERS if x[0] not in picks_names(debts)])
        extra = Debt(name, kind, f"{rng.randint(0, 9999):04d}", _round(rng.uniform(300, 4000)), on_bureau=False)
        debts.append(extra)
        collection = {"agency": rng.choice(AGENCIES), "original": ALIASES[name], "last4": extra.last4,
                      "balance": extra.balance, "duplicate": False}
    first, last = fk.first_name(), fk.last_name()
    postal = fk.postalcode_in_province(prov) if hasattr(fk, "postalcode_in_province") else fk.postalcode()
    h = Household(
        file_id=f"F{i:05d}", packet_date=packet.isoformat(), first=first, last=last,
        street=fk.street_address(), city=fk.city(), province=prov, postal=postal,
        spouse=spouse, spouse_name=fk.first_name() if spouse else "", children=children,
        job=job, spouse_job=spouse_job, side_income=side, side_employer=fk.company() if side else "",
        child_support_paid=support, child_care=care, medical=medical,
        rent=_round(rng.uniform(1100, 2900)), debts=debts, collection=collection, traps=traps)
    stated = monthly_from_pay(job.net, job.frequency)  # the client declares the main job only
    if "intake_understated" in traps:
        stated = _round(stated * rng.uniform(0.62, 0.84))
    h.stated_income = stated
    h.stated_persons = h.persons + (rng.choice([-1, 1]) if h.persons > 1 else 1) if "family_size_mismatch" in traps else h.persons
    h.stated_support = 0.0 if "support_not_declared" in traps else support
    return h


def make_cohort(n: int, seed: int = 7, trap_rate: float = 0.55) -> list[Household]:
    rng = random.Random(seed)
    fk = Faker("en_CA")
    fk.seed_instance(seed)
    return [make_household(i + 1, rng, fk, trap_rate) for i in range(n)]
