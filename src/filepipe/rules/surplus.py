"""Surplus income under Directive No. 11R2-2026, laid out on the Form 65 lines.

Paragraph references are to the Directive. Line numbers follow the OSB guidance for Form 65:
https://ised-isde.canada.ca/site/office-superintendent-bankruptcy/en/instructions-completing-form-65-monthly-income-and-expense-statement-bankruptdebtor-and-family-unit

What this covers: paragraph 5 (core calculation), 6(1) family situation adjustment and 6(2) non-bankrupt
spouse who does not disclose income. What it does not cover: average income reviews under paragraphs 7 and 8,
lump sums and the trustee's judgement. Those stay with the trustee.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .standards import NO_PAYMENT_BELOW, PAYABLE_SHARE, standard_for

NON_DISCRETIONARY = (  # paragraph 5(3) (a) to (h)
    "child_support", "spousal_support", "child_care", "medical", "fines",
    "employment_expenses", "lifted_stay_debt", "non_dischargeable_interest",
)


def _r(x: float) -> float:
    return round(x + 0.0, 2)


@dataclass
class Member:
    """One person in the family unit with net monthly income (after statutory remittances, para 5(2))."""
    net_income: float = 0.0
    non_discretionary: dict = field(default_factory=dict)

    @property
    def nd_total(self) -> float:
        bad = set(self.non_discretionary) - set(NON_DISCRETIONARY)
        if bad:
            raise ValueError(f"not a paragraph 5(3) expense: {sorted(bad)}")
        return sum(self.non_discretionary.values())


@dataclass
class SurplusResult:
    line1_debtor_net_income: float
    line2_other_members_net_income: float
    line3_family_net_income: float
    line4_debtor_non_discretionary: float
    line5_other_non_discretionary: float
    line6_family_non_discretionary: float
    line7_debtor_available: float
    line8_family_available: float
    line9_debtor_share_pct: int
    persons: int
    standard: float
    standard_halved: bool
    family_surplus: float
    debtor_surplus: float
    payable: bool
    line15_monthly_payment: float
    steps: list

    def as_dict(self) -> dict:
        return asdict(self)


def compute(debtor: Member, others: list[Member] | None = None, persons: int = 1,
            spouse_refuses_to_disclose: bool = False) -> SurplusResult:
    others = others or []
    l1 = _r(max(debtor.net_income, 0.0))
    l2 = _r(max(sum(m.net_income for m in others), 0.0))
    l3 = _r(l1 + l2)
    l4 = _r(debtor.nd_total)
    l5 = _r(sum(m.nd_total for m in others))
    l6 = _r(l4 + l5)
    l7 = _r(max(l1 - l4, 0.0))
    l8 = _r(max(l3 - l6, 0.0))
    # the Directive's worked example rounds the share to a percent with two decimals (76.74%)
    share = min(round(l7 / l8, 4), 1.0) if l8 > 0 else 1.0
    std = float(standard_for(persons))
    if spouse_refuses_to_disclose:  # paragraph 6(2)
        std = std * 0.5
    fam_surplus = _r(max(l8 - std, 0.0))
    steps = [
        f"Line 8 family available income {l8:.2f} minus standard for {persons} person(s) {std:.2f} = {fam_surplus:.2f} (para 5(5))",
    ]
    if fam_surplus < NO_PAYMENT_BELOW:  # paragraph 5(6)
        steps.append(f"Surplus {fam_surplus:.2f} is under {NO_PAYMENT_BELOW:.0f}, nothing payable (para 5(6))")
        debtor_surplus, payment, payable = _r(fam_surplus * share), 0.0, False
    else:
        debtor_surplus = _r(fam_surplus * share) if others else fam_surplus  # paragraph 6(1)
        if others:
            steps.append(f"Debtor share {l7:.2f} / {l8:.2f} = {share * 100:.2f}%, {fam_surplus:.2f} x share = {debtor_surplus:.2f} (para 6(1))")
        payment = _r(debtor_surplus * PAYABLE_SHARE)  # paragraph 5(7)
        steps.append(f"{debtor_surplus:.2f} x 50% = {payment:.2f} per month (para 5(7))")
        payable = True
    return SurplusResult(l1, l2, l3, l4, l5, l6, l7, l8, int(round(share * 100)), persons, std,
                         spouse_refuses_to_disclose, fam_surplus, debtor_surplus, payable, payment, steps)


PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}


def monthly_from_pay(net_pay: float, frequency: str) -> float:
    """Average monthly amount from one regular pay, the way a trustee annualises a pay stub."""
    return _r(net_pay * PERIODS_PER_YEAR[frequency] / 12)
