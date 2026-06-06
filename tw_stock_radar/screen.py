"""篩選邏輯: 月K歷史新高狀態分級, 與近5日漲停判斷。"""
from __future__ import annotations

import pandas as pd

from .config import (
    LIMIT_UP_LOOKBACK,
    LIMIT_UP_PCT,
    MIN_HISTORY_MONTHS,
    NEAR_HIGH_FLOOR,
    NEW_HIGH_TOLERANCE,
    PULLBACK_FLOOR,
    PULLBACK_RECENT_MONTHS,
    STATUS_NEAR_HIGH,
    STATUS_NEW_HIGH,
    STATUS_PULLBACK,
    TREND_MA_MONTHS,
)


def classify_status(monthly: pd.DataFrame | None) -> dict | None:
    """依還原月K判斷歷史新高狀態。不符合任何狀態或資料不足回 None。

    dist = 最新還原收盤 / 歷史最高月High - 1
    """
    if monthly is None or len(monthly) < MIN_HISTORY_MONTHS:
        return None
    high = monthly["High"]
    close = monthly["Close"]
    ath = float(high.max())
    if not ath or ath <= 0:
        return None
    last = float(close.iloc[-1])
    dist = last / ath - 1.0
    months_since_ath = (len(high) - 1) - int(high.to_numpy().argmax())
    ma = float(close.tail(TREND_MA_MONTHS).mean())

    if dist >= -NEW_HIGH_TOLERANCE:
        status = STATUS_NEW_HIGH
    elif dist >= NEAR_HIGH_FLOOR:
        status = STATUS_NEAR_HIGH
    elif dist >= PULLBACK_FLOOR and months_since_ath <= PULLBACK_RECENT_MONTHS:
        status = STATUS_PULLBACK
    else:
        return None

    # 趨勢健全度: 收盤需站上 12 月均線, 過濾下降趨勢中的假高檔。
    if last < ma:
        return None

    return {
        "status": status,
        "ath": ath,
        "last_adj": last,
        "dist": dist,
        "months_since_ath": months_since_ath,
    }


def evaluate_monthly(codes: list[str],
                     monthly_hist: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """對每個代號做歷史新高分級, 回傳通過者的指標表。"""
    rows = []
    for code in codes:
        metrics = classify_status(monthly_hist.get(code))
        if metrics:
            metrics["code"] = code
            rows.append(metrics)
    cols = ["code", "status", "ath", "last_adj", "dist", "months_since_ath"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]


def recent_limit_up(daily: pd.DataFrame | None) -> tuple[bool, int]:
    """近 LIMIT_UP_LOOKBACK 個交易日是否曾(收盤)漲停, 與次數。用原始日價。"""
    if daily is None or len(daily) < 2:
        return False, 0
    close = daily["Close"].dropna()
    pct = close.pct_change() * 100.0
    window = pct.tail(LIMIT_UP_LOOKBACK)
    hits = int((window >= LIMIT_UP_PCT).sum())
    return hits > 0, hits


def compute_limit_up(codes: list[str],
                     daily_hist: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for code in codes:
        up, cnt = recent_limit_up(daily_hist.get(code))
        rows.append({"code": code, "limit_up": up, "limit_up_count": cnt})
    if not rows:
        return pd.DataFrame(columns=["code", "limit_up", "limit_up_count"])
    return pd.DataFrame(rows)
