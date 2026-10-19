"""Directive 11R2-2026 Appendix B examples, worked to the cent."""
import pytest

from filepipe.rules.standards import STANDARDS_2026, standard_for
from filepipe.rules.surplus import Member, compute, monthly_from_pay


def test_standards_table_2026():
    assert STANDARDS_2026 == {1: 2716, 2: 3381, 3: 4157, 4: 5047, 5: 5724, 6: 6456, 7: 7188}
    assert standard_for(9) == 7188


def test_example_1_family_situation_adjustment():
    r = compute(Member(3300), [Member(1000)], persons=2)
    assert r.line8_family_available == 4300
    assert r.family_surplus == 919
    assert r.debtor_surplus == pytest.approx(705.24, abs=0.01)
    assert r.line15_monthly_payment == pytest.approx(352.62, abs=0.01)
    assert r.line9_debtor_share_pct == 77


def test_example_2_below_standard_pays_nothing():
    r = compute(Member(2500), persons=1)
    assert r.family_surplus == 0 and r.line15_monthly_payment == 0 and not r.payable


def test_example_2_after_increase_average_income():
    r = compute(Member(round(23500 / 7, 2)), persons=1)
    assert r.family_surplus == pytest.approx(641.14, abs=0.01)
    assert r.line15_monthly_payment == pytest.approx(320.57, abs=0.01)


def test_example_3_single_with_surplus():
    r = compute(Member(3500), persons=1)
    assert r.family_surplus == 784 and r.line15_monthly_payment == 392


def test_example_6_spouse_refuses_to_disclose():
    r = compute(Member(3000), persons=4, spouse_refuses_to_disclose=True)
    assert r.standard == 2523.5
    assert r.family_surplus == 476.5
    assert r.line15_monthly_payment == 238.25


def test_under_200_threshold_is_strict():
    assert compute(Member(2716 + 199.99)).line15_monthly_payment == 0
    assert compute(Member(2716 + 200)).line15_monthly_payment == 100


def test_non_discretionary_expenses_reduce_available_income():
    r = compute(Member(4000, {"child_support": 500, "child_care": 300}), persons=2)
    assert r.line7_debtor_available == 3200
    assert r.family_surplus == 0


def test_unknown_expense_type_is_refused():
    with pytest.raises(ValueError):
        compute(Member(4000, {"car_payment": 500}))


@pytest.mark.parametrize("freq,expected", [("biweekly", 2166.67), ("semimonthly", 2000.0), ("weekly", 4333.33), ("monthly", 1000.0)])
def test_monthly_from_pay(freq, expected):
    pay = {"biweekly": 1000, "semimonthly": 1000, "weekly": 1000, "monthly": 1000}[freq]
    assert monthly_from_pay(pay, freq) == pytest.approx(expected, abs=0.01)
