"""Superintendent's Standards for 2026, Directive No. 11R2-2026, Appendix A.

Source: https://ised-isde.canada.ca/site/office-superintendent-bankruptcy/en/directive-no-11r2-2026-surplus-income
Monthly amounts in dollars by number of persons in the family unit. 7 or more persons use the 7+ row.
"""

YEAR = 2026
SOURCE = "https://ised-isde.canada.ca/site/office-superintendent-bankruptcy/en/directive-no-11r2-2026-surplus-income"

STANDARDS_2026 = {1: 2716, 2: 3381, 3: 4157, 4: 5047, 5: 5724, 6: 6456, 7: 7188}

# paragraph 5(6) and 5(7)
NO_PAYMENT_BELOW = 200.0
PAYABLE_SHARE = 0.50


def standard_for(persons: int) -> int:
    if persons < 1:
        raise ValueError("a family unit has at least one person")
    return STANDARDS_2026[min(persons, 7)]
