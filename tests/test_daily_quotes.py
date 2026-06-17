"""daily_quotes.py 測試: TWSE 盤後傍晚把日期回報成「次一營業日」時要被擋下。

真實災情 (2026-06-17 傍晚): TWSE MI_INDEX 回應的 date 欄標成 06-18,
程式直接採信 -> 資料日期變明天, 日期一致性防呆又以 06-18 為基準, 反把
正確日期 (06-17) 的上櫃股整批丟光 (上櫃 9 檔全消失)。
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

from tw_stock_radar import daily_quotes

_TPE = timezone(timedelta(hours=8))


def _twse_payload(date_str: str) -> dict:
    """組一張最小可用的 MI_INDEX 表, date 欄可指定 (用來塞未來日期)。"""
    return {
        "stat": "OK",
        "date": date_str,
        "tables": [{
            "fields": ["證券代號", "證券名稱", "成交股數", "成交金額",
                       "收盤價", "漲跌(+/-)", "漲跌價差"],
            "data": [["2330", "台積電", "1000", "1000000", "1000",
                      "<p style='color:red'>+</p>", "5"]],
        }],
    }


def test_twse_daily_rejects_future_date(monkeypatch):
    """TWSE 回報未來日期時, 應改用實際查詢的交易日 (今天), 不採信未來日。"""
    future = (datetime.now(_TPE).date() + timedelta(days=1)).strftime("%Y%m%d")
    monkeypatch.setattr(daily_quotes, "get_json",
                        lambda url, sess: _twse_payload(future))

    df = daily_quotes.fetch_twse_daily(session=object())

    today = datetime.now(_TPE).date()
    assert (df["date"].dt.date <= today).all()  # 不該出現未來日期
    assert df["date"].iloc[0].date() == today


def test_daily_quotes_keeps_tpex_when_twse_future(monkeypatch):
    """防呆基準不該鎖到未來日期, 否則正確日期的上櫃股會被整批丟掉。"""
    today = pd.Timestamp(datetime.now(_TPE).date())
    tomorrow = today + pd.Timedelta(days=1)

    twse = pd.DataFrame({
        "code": ["2330"], "name": ["台積電"], "market": ["TWSE"],
        "date": [tomorrow],  # TWSE 誤標成明天
        "close": [1000.0], "change": [5.0], "change_pct": [0.5],
        "trade_value": [1e6], "trade_volume": [1e3], "next_limit_up": [float("nan")],
    })
    tpex = pd.DataFrame({
        "code": ["6488"], "name": ["環球晶"], "market": ["TPEX"],
        "date": [today],  # 上櫃日期正確
        "close": [500.0], "change": [3.0], "change_pct": [0.6],
        "trade_value": [5e5], "trade_volume": [5e2], "next_limit_up": [550.0],
    })
    monkeypatch.setattr(daily_quotes, "fetch_twse_daily", lambda s=None: twse)
    monkeypatch.setattr(daily_quotes, "fetch_tpex_daily", lambda s=None: tpex)

    df = daily_quotes.fetch_daily_quotes(session=object())

    # 重點: 基準不該鎖到未來日期 (明天), 害正確日期的上櫃股被整批丟掉。
    assert "TPEX" in set(df["market"])
    assert "6488" in set(df["code"])
