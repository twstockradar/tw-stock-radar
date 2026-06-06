"""抓取當日全市場行情 (上市 TWSE + 上櫃 TPEX)。

回傳欄位: code, name, market, close, change, change_pct, trade_value,
trade_volume, next_limit_up (上櫃才有)。
"""
from __future__ import annotations

import pandas as pd

from .util import get_json, roc_to_date, to_float

TWSE_DAILY = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_DAILY = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def _change_pct(close: float, change: float) -> float:
    """由收盤價與漲跌價差推算漲跌幅 (%)。"""
    prev = close - change
    if not prev or pd.isna(prev) or prev <= 0:
        return float("nan")
    return change / prev * 100.0


def fetch_twse_daily(session=None) -> pd.DataFrame:
    data = get_json(TWSE_DAILY, session)
    rows = []
    for r in data:
        close = to_float(r.get("ClosingPrice"))
        change = to_float(r.get("Change"))
        rows.append({
            "code": str(r.get("Code", "")).strip(),
            "name": str(r.get("Name", "")).strip(),
            "market": "TWSE",
            "date": roc_to_date(r.get("Date")),
            "close": close,
            "change": change,
            "change_pct": _change_pct(close, change),
            "trade_value": to_float(r.get("TradeValue")),
            "trade_volume": to_float(r.get("TradeVolume")),
            "next_limit_up": float("nan"),
        })
    return pd.DataFrame(rows)


def fetch_tpex_daily(session=None) -> pd.DataFrame:
    data = get_json(TPEX_DAILY, session)
    rows = []
    for r in data:
        close = to_float(r.get("Close"))
        change = to_float(r.get("Change"))
        rows.append({
            "code": str(r.get("SecuritiesCompanyCode", "")).strip(),
            "name": str(r.get("CompanyName", "")).strip(),
            "market": "TPEX",
            "date": roc_to_date(r.get("Date")),
            "close": close,
            "change": change,
            "change_pct": _change_pct(close, change),
            "trade_value": to_float(r.get("TransactionAmount")),
            "trade_volume": to_float(r.get("TradingShares")),
            "next_limit_up": to_float(r.get("NextLimitUp")),
        })
    return pd.DataFrame(rows)


def fetch_daily_quotes(session=None) -> pd.DataFrame:
    """合併上市+上櫃當日行情。只保留有有效收盤價的個股。"""
    frames = []
    for fetch in (fetch_twse_daily, fetch_tpex_daily):
        try:
            frames.append(fetch(session))
        except Exception as err:  # noqa: BLE001
            print(f"[daily_quotes] 警告: {fetch.__name__} 失敗: {err}")
    if not frames:
        raise RuntimeError("無法取得任何當日行情資料")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["close"].notna() & (df["close"] > 0)].reset_index(drop=True)
    return df
