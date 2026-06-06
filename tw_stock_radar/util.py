"""共用工具:HTTP 取得、民國日期轉換、數值解析與格式化。"""
from __future__ import annotations

import time

import pandas as pd
import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) TW_STOCK_RADAR/0.1"
)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def get_json(url: str, session: requests.Session | None = None,
             retries: int = 3, timeout: int = 30):
    """GET 一個 JSON 端點, 失敗自動重試。"""
    sess = session or make_session()
    last_err: Exception | None = None
    for i in range(retries):
        try:
            resp = sess.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET 失敗: {url}: {last_err}")


def roc_to_date(value) -> pd.Timestamp:
    """民國日期字串 -> Timestamp。支援 '1150604' 與 '115/06/04'。"""
    s = str(value).strip().replace("/", "")
    if len(s) < 6:
        return pd.NaT
    try:
        day = int(s[-2:])
        month = int(s[-4:-2])
        year = int(s[:-4]) + 1911
        return pd.Timestamp(year=year, month=month, day=day)
    except Exception:  # noqa: BLE001
        return pd.NaT


def to_float(x) -> float:
    """把 API 回傳的字串數值安全轉 float;無效值回 NaN。"""
    if x is None:
        return float("nan")
    s = str(x).replace(",", "").strip()
    if s in ("", "--", "-", "N/A", "null", "None"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def format_amount(v) -> str:
    """金額 (NTD) -> 億/萬 易讀字串。"""
    if v is None or pd.isna(v):
        return "-"
    v = float(v)
    if abs(v) >= 1e12:
        return f"{v / 1e12:.2f}兆"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.1f}億"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.0f}萬"
    return f"{v:.0f}"
