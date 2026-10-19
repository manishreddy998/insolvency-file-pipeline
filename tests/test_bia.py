from datetime import date

from filepipe.rules import bia, fees


def test_three_payments_behind_is_annulled():
    assert not bia.is_deemed_annulled(paid_total=800, due_total=1000, payment=100)
    assert bia.is_deemed_annulled(paid_total=700, due_total=1000, payment=100)
    assert bia.is_deemed_annulled(paid_total=600, due_total=900.004, payment=100)


def test_amendment_stops_the_clock():
    assert not bia.is_deemed_annulled(paid_total=0, due_total=900, payment=100, amendment_filed=True)


def test_partial_payments_count_toward_default():
    # 2.5 payments behind is not yet three
    assert bia.payments_left_before_annulment(paid_total=750, due_total=1000, payment=100) == 0.5


def test_dates():
    filed = date(2026, 1, 15)
    assert bia.deemed_acceptance_date(filed) == date(2026, 3, 1)
    w = bia.counselling_windows(filed)
    assert w["first_session_from"] == date(2026, 1, 25) and w["first_session_by"] == date(2026, 4, 15)


def test_rule_129_fees():
    assert fees.proposal_fees(0) == 1500
    assert fees.proposal_fees(10000) == 3500
    s = fees.split_payments(12000)
    assert s["distributed"] == 10000 and s["distribution_fee"] == 2000
