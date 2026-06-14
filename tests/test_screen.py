"""screen.py 篩選邏輯測試: 月K歷史新高分級、近5日漲停。"""
import pandas as pd

from tw_stock_radar.screen import classify_status, recent_limit_up


def _monthly(closes):
    """以收盤序列建月K (High=Close, 簡化)。"""
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="MS")
    return pd.DataFrame({"High": closes, "Close": closes,
                         "Open": closes, "Low": closes}, index=idx)


def test_new_high_status():
    m = _monthly(list(range(100, 120)))  # 20 根, 最後一根即歷史最高
    res = classify_status(m)
    assert res is not None
    assert res["status"] == "NEW_HIGH"
    assert abs(res["dist"]) < 1e-9


def test_below_pullback_floor_returns_none():
    # 前高 119 出現在早期, 最後跌到 90 -> dist 約 -24% < -15% -> 不符任何狀態
    closes = list(range(100, 120)) + [90]
    assert classify_status(_monthly(closes)) is None


def test_insufficient_history_returns_none():
    assert classify_status(_monthly(list(range(100, 105)))) is None  # 只有 5 根


def test_below_ma_filtered_out():
    # 最後一根創新高但長期均線在其上方 (一路下跌後尾段彈高仍 < MA) 的反例:
    # 構造前段很高 -> MA 高 -> 最後雖等於 ATH 但... 這裡改測單純站不上均線。
    closes = [200] * 12 + [100, 100, 100, 100, 100, 130]  # MA 偏高, 末根 130 < MA
    res = classify_status(_monthly(closes))
    assert res is None


def test_recent_limit_up_detects_jump():
    daily = pd.DataFrame({"Close": [100, 100, 100, 100, 110]})
    up, count = recent_limit_up(daily)
    assert up is True
    assert count == 1


def test_recent_limit_up_none_when_flat():
    daily = pd.DataFrame({"Close": [100, 101, 100, 101, 100]})
    up, count = recent_limit_up(daily)
    assert up is False
    assert count == 0
