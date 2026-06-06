"""還原權值月K歷史 (算歷史新高 + 畫圖) 與近日原始日K (算漲停)。

- 月K: yfinance interval='1mo', auto_adjust=True (還原權值)。
- 以 parquet 快取, 缺的抓全歷史、舊的只補近月, 避免每天重抓全市場。
- 日K: yfinance interval='1d', auto_adjust=False (原始價, 對應實際漲停)。
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from .config import DATA_DIR, HISTORY_PARQUET

_OHLC = ["Open", "High", "Low", "Close"]


def yf_symbol(code: str, market: str) -> str:
    return f"{code}.TWO" if market == "TPEX" else f"{code}.TW"


def _download(symbols: list[str], *, interval: str, period: str,
              auto_adjust: bool, batch: int = 150) -> dict[str, pd.DataFrame]:
    """批次下載, 回傳 {symbol: OHLC DataFrame}。"""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        try:
            data = yf.download(
                chunk, period=period, interval=interval,
                auto_adjust=auto_adjust, group_by="ticker",
                threads=True, progress=False,
            )
        except Exception as err:  # noqa: BLE001
            print(f"[history] 批次下載失敗 ({i}-{i+len(chunk)}): {err}")
            continue
        if data is None or len(data) == 0:
            continue
        for sym in chunk:
            try:
                sub = data if len(chunk) == 1 else data[sym]
                sub = sub[_OHLC].dropna(how="all").dropna()
                if sub.empty:
                    continue
                sub.index = pd.to_datetime(sub.index)
                sub.index.name = "date"
                out[sym] = sub
            except Exception:  # noqa: BLE001
                continue
    return out


# ---------- 月K 歷史 (含快取) ----------

def _load_cache() -> dict[str, pd.DataFrame]:
    if not HISTORY_PARQUET.exists():
        return {}
    try:
        long = pd.read_parquet(HISTORY_PARQUET)
    except Exception as err:  # noqa: BLE001
        print(f"[history] 快取讀取失敗, 視為無快取: {err}")
        return {}
    cache: dict[str, pd.DataFrame] = {}
    for code, g in long.groupby("code"):
        d = g.set_index("date")[_OHLC].sort_index()
        cache[str(code)] = d
    return cache


def _save_cache(cache: dict[str, pd.DataFrame]) -> None:
    frames = []
    for code, df in cache.items():
        t = df.reset_index()
        t["code"] = code
        frames.append(t)
    if not frames:
        return
    long = pd.concat(frames, ignore_index=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    long.to_parquet(HISTORY_PARQUET, index=False)


def _is_stale(df: pd.DataFrame) -> bool:
    """快取是否需更新 (最後一根不是本月)。"""
    if df is None or df.empty:
        return True
    last = df.index.max()
    now = pd.Timestamp.now()
    return not (last.year == now.year and last.month == now.month)


def _merge_tail(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new
    cutoff = new.index.min()
    keep = old[old.index < cutoff]
    merged = pd.concat([keep, new])
    return merged[~merged.index.duplicated(keep="last")].sort_index()


def get_monthly_history(codes_markets: list[tuple[str, str]]) -> dict[str, pd.DataFrame]:
    """取得各代號還原月K (優先用快取, 缺漏補抓)。回傳 {code: monthly OHLC}。"""
    cache = _load_cache()
    sym_to_code = {yf_symbol(c, m): c for c, m in codes_markets}

    missing = [s for s, c in sym_to_code.items() if c not in cache]
    stale = [s for s, c in sym_to_code.items()
             if c in cache and _is_stale(cache[c])]

    if missing:
        print(f"[history] 全歷史抓取 {len(missing)} 檔...")
        full = _download(missing, interval="1mo", period="max", auto_adjust=True)
        for sym, df in full.items():
            cache[sym_to_code[sym]] = df
    if stale:
        print(f"[history] 增量更新 {len(stale)} 檔近月...")
        recent = _download(stale, interval="1mo", period="6mo", auto_adjust=True)
        for sym, df in recent.items():
            code = sym_to_code[sym]
            cache[code] = _merge_tail(cache.get(code), df)

    if missing or stale:
        _save_cache(cache)

    return {c: cache[c] for c in sym_to_code.values() if c in cache}


# ---------- 近日原始日K (算漲停) ----------

def get_recent_daily(codes_markets: list[tuple[str, str]],
                     period: str = "2mo") -> dict[str, pd.DataFrame]:
    """近日原始(未還原)日K, 用來判斷漲停。回傳 {code: daily OHLC}。"""
    sym_to_code = {yf_symbol(c, m): c for c, m in codes_markets}
    raw = _download(list(sym_to_code), interval="1d", period=period,
                    auto_adjust=False)
    return {sym_to_code[s]: df for s, df in raw.items()}
