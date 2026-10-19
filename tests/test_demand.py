from datetime import date

import numpy as np
import openpyxl
import pandas as pd

from filepipe.demand import backtest, clean_fsa, load, monthly, seasonal_naive, seasonal_trend


def _sheet(wb, name, month, rows):
    ws = wb.create_sheet(name)
    ws.append(["Office of the Superintendent of Bankruptcy"])
    ws.append(["Provincial Breakdown by Forward Sortation Area"])
    ws.append([f"Month: {month}"])
    for _ in range(7):
        ws.append([None])
    for code, cb, cp in rows:
        ws.append([code, cb, 0, 1000, 0, 0, 0, cp, 0, 2000, 0, 0, 0])
    ws.append(["Total", sum(r[1] for r in rows), 0, 0, 0, 0, 0, sum(r[2] for r in rows), 0, 0, 0, 0, 0])


def test_reads_layout_and_reconciles_totals(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "Notes"
    _sheet(wb, "ONT_ONT (1)", "January 2026", [("M1B", 2, 5), ("KOK", 1, 1), ("M16", 0, 1)])
    _sheet(wb, "SAS_SAS (1)", "January 2026", [("S4P", 1, 2)])
    wb.save(tmp_path / "f.xlsx")
    df, checks = load(tmp_path)
    assert all(c["ok"] for c in checks) and len(checks) == 2
    assert set(df["province"]) == {"ON", "SK"}
    on = df[df["province"] == "ON"].set_index("fsa")["consumer_insolvencies"].to_dict()
    assert on == {"K0K": 2.0, "M1B": 7.0, "???": 1.0}
    assert df["month"].iloc[0] == date(2026, 1, 1)


def test_clean_fsa():
    assert clean_fsa("k0a") == "K0A"
    assert clean_fsa("KOK") == "K0K"
    assert clean_fsa("M16") == "???"
    assert clean_fsa("D1A") == "???"  # D is never a first letter


def _series(n=36, growth=0.0):
    idx = [(pd.Timestamp("2023-01-01") + pd.DateOffset(months=i)).date() for i in range(n)]
    season = np.array([10, 12, 14, 13, 12, 11, 10, 9, 12, 13, 11, 8], float)
    vals = [season[i % 12] * (1 + growth) ** (i // 12) * 10 for i in range(n)]
    return pd.DataFrame({"x": vals}, index=idx)


def test_seasonal_naive_is_exact_on_a_flat_year():
    bt = backtest(_series())
    assert bt["seasonal-naive"]["mape"] == 0


def test_trend_helps_when_the_level_grows():
    w = _series(growth=0.2)
    bt = backtest(w)
    assert bt["seasonal-trend"]["mape"] < bt["seasonal-naive"]["mape"]
    assert seasonal_trend(w, 6).shape == seasonal_naive(w, 6).shape == (6, 1)


def test_monthly_fills_missing_months():
    df = pd.DataFrame({"month": [date(2026, 1, 1), date(2026, 3, 1)], "fsa": ["A", "A"], "consumer_insolvencies": [1, 2]})
    assert monthly(df).shape[0] == 3
