from filepipe.extract.parse import parse_date, parse_money, parse_postal


def test_money_with_ocr_slips():
    assert parse_money("Net Pay: $1,266.2O") == 1266.20
    assert parse_money("Gross Pay: $1,2S6.14") == 1256.14
    assert parse_money("Amount owing: $1,808,70") == 1808.70
    assert parse_money("PAYROLL DEP HUNT, SCHWARTZ AND CHAVEZ 859.20") == 859.20
    assert parse_money("None") is None


def test_strict_money_refuses_slips():
    assert parse_money("Net Pay: $1,266.2O", repair=False) is None
    assert parse_money("Net Pay: $1,266.20", repair=False) == 1266.20


def test_dates_in_every_layout():
    assert parse_date("2026-09-13") == "2026-09-13"
    assert parse_date("Sep 13, 2026") == "2026-09-13"
    assert parse_date("13/09/2026") == "2026-09-13"
    assert parse_date("September 13, 2026") == "2026-09-13"
    assert parse_date("20/08/202") is None


def test_postal_repair():
    assert parse_postal("Postal code: K2J 9P2") == "K2J 9P2"
    assert parse_postal("postal code: m5v 0b1") == "M5V 0B1"
    assert parse_postal("L4N8B1") == "L4N 8B1"
    assert parse_postal("L4N 8B1") == "L4N 8B1"
