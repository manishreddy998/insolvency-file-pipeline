"""Clocks from the Bankruptcy and Insolvency Act that shape a consumer proposal file.

- s. 66.31(1)(a): with monthly payments, a consumer proposal is deemed annulled on the day the debtor is in
  default for an amount equal to or more than three payments, unless an amendment was filed first.
  https://laws-lois.justice.gc.ca/eng/acts/b-3/page-14.html
- s. 66.18: deemed acceptance 45 days after filing unless a meeting of creditors is requested.
  https://laws-lois.justice.gc.ca/eng/acts/B-3/section-66.18.html
- Directive 1R8: first counselling session 10 to 90 days after filing, second at least 30 days later.
  https://www.ised-isde.canada.ca/site/office-superintendent-bankruptcy/en/directive-no-1r8-counselling-insolvency-matters
"""
from __future__ import annotations

from datetime import date, timedelta

ANNUL_AFTER_PAYMENTS = 3
DEEMED_ACCEPTANCE_DAYS = 45
COUNSEL_FIRST = (10, 90)
COUNSEL_GAP_DAYS = 30


def arrears_in_payments(paid_total: float, due_total: float, payment: float) -> float:
    """How many monthly payments the debtor is behind by."""
    if payment <= 0:
        return 0.0
    return max(due_total - paid_total, 0.0) / payment


def is_deemed_annulled(paid_total: float, due_total: float, payment: float, amendment_filed: bool = False) -> bool:
    if amendment_filed:
        return False
    # a cent of rounding must not trigger an annulment
    return arrears_in_payments(paid_total, due_total, payment) >= ANNUL_AFTER_PAYMENTS - 1e-9


def payments_left_before_annulment(paid_total: float, due_total: float, payment: float) -> float:
    return max(ANNUL_AFTER_PAYMENTS - arrears_in_payments(paid_total, due_total, payment), 0.0)


def deemed_acceptance_date(filed: date) -> date:
    return filed + timedelta(days=DEEMED_ACCEPTANCE_DAYS)


def counselling_windows(filed: date) -> dict:
    first_open, first_close = filed + timedelta(days=COUNSEL_FIRST[0]), filed + timedelta(days=COUNSEL_FIRST[1])
    return {"first_session_from": first_open, "first_session_by": first_close,
            "second_session_not_before": first_open + timedelta(days=COUNSEL_GAP_DAYS)}
