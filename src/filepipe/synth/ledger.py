"""Synthetic consumer proposal payment ledger. Labelled outcomes: completed, annulled, active.

The simulation is simple on purpose and stated in the README: income shocks raise the chance of late, partial
and missed payments, and a proposal is deemed annulled when the debtor is three payments behind (BIA 66.31).
Nothing here is calibrated to real Farber or OSB outcomes.
"""
from __future__ import annotations

import math
import random
from datetime import date

import numpy as np
import pandas as pd

INCOME_TYPES = {"salaried": 0.004, "hourly": 0.009, "self_employed": 0.015, "gig": 0.020}  # monthly shock hazard
AS_OF = date(2026, 9, 30)


def _months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _add(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, 1)


def simulate(n: int = 5000, seed: int = 11) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    files, months = [], []
    for i in range(n):
        start = _add(date(2021, 1, 1), rng.randint(0, _months(date(2021, 1, 1), date(2026, 8, 1))))
        itype = rng.choices(list(INCOME_TYPES), [0.45, 0.3, 0.15, 0.10])[0]
        income = rng.uniform(2200, 6500)
        pti = min(max(nprng.normal(0.09, 0.035), 0.03), 0.22)
        pay = round(income * pti / 5) * 5
        term = rng.choices([60, 48, 36], [0.7, 0.2, 0.1])[0]
        flags = rng.choices([0, 1, 2], [0.62, 0.28, 0.10])[0]  # findings from the intake proof checks
        prior = rng.random() < 0.10
        pad = rng.random() < 0.8  # pre-authorized debit vs manual transfer
        support = rng.random() < 0.12
        persons = rng.choices([1, 2, 3, 4, 5], [0.38, 0.24, 0.18, 0.14, 0.06])[0]
        frailty = 1.0 + 0.5 * flags + (0.6 if prior else 0) + (0.3 if not pad else 0) + 6 * max(pti - 0.1, 0)
        due = paid = 0.0
        strain = stress = 0
        outcome = "active"
        end_month = None
        amended = False
        for m in range(1, term + 1):
            month = _add(start, m)
            if month > AS_OF.replace(day=1):
                break
            due += pay
            if strain == 0 and stress == 0 and rng.random() < INCOME_TYPES[itype] * frailty:
                strain = rng.randint(1, 3)  # an income shock shows first as late, bounced or short payments
            # behaviour this month
            if stress:
                p_miss = 0.30 + 0.08 * flags
                p_partial, p_late, p_nsf, p_contact = 0.30, 0.6, 0.45 if pad else 0.0, 0.25
                stress -= 1
            elif strain:
                p_miss = 0.04
                p_partial, p_late, p_nsf, p_contact = 0.35, 0.7, 0.5 if pad else 0.0, 0.3
                strain -= 1
                if strain == 0 and rng.random() < 0.65:
                    stress = rng.randint(2, 8)  # most strained files go on to miss payments; some recover
            else:
                p_miss, p_partial, p_late, p_nsf, p_contact = 0.015 * frailty, 0.03, 0.08, 0.03 if pad else 0.0, 0.03
            nsf = rng.random() < p_nsf
            contact = rng.random() < p_contact
            if rng.random() < p_miss:
                amount, late = 0.0, 0
            elif rng.random() < p_partial:
                amount, late = round(pay * rng.uniform(0.3, 0.8), 2), rng.randint(3, 25)
            else:
                amount = pay
                late = rng.randint(1, 20) if rng.random() < p_late or nsf else 0
                arrears = due - paid - amount
                if arrears > 0 and not stress and rng.random() < 0.55:
                    amount += min(arrears, pay)  # catching up after a slip
            paid += amount
            arrears_n = max(due - paid, 0) / pay
            months.append({"file_id": f"P{i:05d}", "month": month.isoformat(), "m": m, "due": pay,
                           "paid": round(amount, 2), "days_late": late, "nsf": int(nsf), "contact": int(contact),
                           "partial": int(0 < amount < pay), "missed": int(amount == 0),
                           "arrears_payments": round(arrears_n, 3)})
            if arrears_n >= 3 - 1e-9:
                if contact and not amended and rng.random() < 0.3:
                    amended = True  # an amendment filed in time stops the clock and resets the plan
                    paid = due
                    stress = strain = 0
                    continue
                outcome, end_month = "annulled", month
                break
            if paid >= pay * term - 1e-6:
                outcome, end_month = "completed", month
                break
        files.append({"file_id": f"P{i:05d}", "start": start.isoformat(), "income_type": itype,
                      "monthly_income": round(income, 2), "payment": pay, "term": term,
                      "payment_to_income": round(pay / income, 4), "intake_flags": flags, "prior_insolvency": int(prior),
                      "pad": int(pad), "support_obligation": int(support), "persons": persons, "amended": int(amended),
                      "outcome": outcome, "end_month": end_month.isoformat() if end_month else None,
                      "paid_total": round(paid, 2)})
    return pd.DataFrame(files), pd.DataFrame(months)
