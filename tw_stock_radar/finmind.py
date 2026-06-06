"""FinMind 備援資料源: 當 yfinance 抓不到時改用 FinMind。

需環境變數 FINMIND_TOKEN (到 finmindtrade.com 免費註冊取得); 未設定則停用備援。
- 還原月K: dataset TaiwanStockPriceAdj -> 月線 OHLC (算歷史新高 + 畫圖)
- 近日原始日K: dataset TaiwanStockPrice -> 判斷漲停
FinMind 欄位: date, open, max(高), min(低), close。
"""
from __future__ import annotations

import os

import pandas as pd

from .util import get_json

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _token() -> str:
    return os.environ.get("FINMIND_TOKEN", "").strip()


def available() -> bool:
    return bool(_token())


def _fetch(dataset: str, code: str, start: str, session=None) -> pd.DataFrame | None:
    token = _token()
    if not token:
        return None
    url = (f"{FINMIND_URL}?dataset={dataset}&data_id={code}"
           f"&start_date={start}&token={token}")
    try:
        data = get_json(url, session, retries=2, timeout=30)
    except Exception as err:  # noqa: BLE001
        print(f"[finmind] {dataset} {code} 取得失敗: {err}")
        return None
    if not isinstance(data, dict) or data.get("status") != 200:
        return None
    rows = data.get("data") or []
    return pd.DataFrame(rows) if rows else None


def _to_ohlc(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if not {"date", "open", "max", "min", "close"}.issubset(df.columns):
        return None
    out = pd.DataFrame({
        "Open": pd.to_numeric(df["open"], errors="coerce"),
        "High": pd.to_numeric(df["max"], errors="coerce"),
        "Low": pd.to_numeric(df["min"], errors="coerce"),
        "Close": pd.to_numeric(df["close"], errors="coerce"),
    })
    out.index = pd.to_datetime(df["date"], errors="coerce")
    out.index.name = "date"
    return out.dropna().sort_index()


def monthly_adjusted(code: str, session=None, start: str = "2005-01-01") -> pd.DataFrame | None:
    """還原月K (月 OHLC)。"""
    daily = _to_ohlc(_fetch("TaiwanStockPriceAdj", code, start, session))
    if daily is None or daily.empty:
        return None
    grp = daily.groupby(daily.index.to_period("M")).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"})
    grp.index = grp.index.to_timestamp()
    grp.index.name = "date"
    return grp if not grp.empty else None


def recent_daily_raw(code: str, session=None) -> pd.DataFrame | None:
    """近約 80 日原始日K (判斷漲停)。"""
    start = (pd.Timestamp.now() - pd.Timedelta(days=80)).strftime("%Y-%m-%d")
    return _to_ohlc(_fetch("TaiwanStockPrice", code, start, session))
