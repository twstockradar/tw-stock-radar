"""util.py 純函式測試: 民國日期、數值解析、金額格式化。"""
import math

import pandas as pd

from tw_stock_radar.util import format_amount, roc_to_date, to_float


def test_roc_to_date_compact():
    assert roc_to_date("1150604") == pd.Timestamp(2026, 6, 4)


def test_roc_to_date_with_slash():
    assert roc_to_date("115/06/04") == pd.Timestamp(2026, 6, 4)


def test_roc_to_date_invalid():
    assert roc_to_date("123") is pd.NaT
    assert roc_to_date("") is pd.NaT


def test_to_float_thousands_separator():
    assert to_float("1,234.5") == 1234.5


def test_to_float_placeholders_are_nan():
    for bad in ("--", "-", "", "N/A", None):
        assert math.isnan(to_float(bad))


def test_format_amount():
    assert format_amount(5_000_000_000) == "50.0億"
    assert format_amount(1.5e12) == "1.50兆"
    assert format_amount(30_000) == "3萬"
    assert format_amount(500) == "500"
    assert format_amount(float("nan")) == "-"
