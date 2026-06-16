"""還原權值月K歷史 (算歷史新高 + 畫圖) 與近日原始日K (算漲停)。

- 月K: yfinance interval='1mo', auto_adjust=True (還原權值)。
- 以 parquet 快取, 缺的抓全歷史、舊的只補近月, 避免每天重抓全市場。
- 日K: yfinance interval='1d', auto_adjust=False (原始價, 對應實際漲停)。
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from . import finmind
from .config import DATA_DIR, HISTORY_PARQUET
from .util import make_session

_OHLC = ["Open", "High", "Low", "Close"]


def yf_symbol(code: str, market: str) -> str:
    return f"{code}.TWO" if market == "TPEX" else f"{code}.TW"


def _norm_dt_index(index) -> pd.DatetimeIndex:
    """統一日期索引為 tz-naive、奈秒(ns)解析度。

    兩個必要: (1) yfinance 偶爾回傳帶時區的索引; (2) pyarrow 把快取日期存成
    微秒(us), 讀回是 us, 與 yfinance 新抓的 ns 混在同一個 pd.concat 會炸
    (numpy 維度不符)。一律轉成 tz-naive ns, 讓快取/新抓/合併全程一致。
    """
    idx = pd.to_datetime(index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    return idx.astype("datetime64[ns]")


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
                sub.index = _norm_dt_index(sub.index)
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
        # parquet 讀回的日期是 us; 統一成 ns, 免得與新抓的 ns 合併時崩潰。
        d.index = _norm_dt_index(d.index)
        cache[str(code)] = d
    return cache


def _save_cache(cache: dict[str, pd.DataFrame]) -> None:
    frames = []
    for code, df in cache.items():
        try:
            # 先去重複欄位: yfinance 偶爾回傳重複的 OHLC 欄, 選取後該欄變 2-D,
            # 會讓整批 concat 崩潰 (InvalidIndexError / numpy 維度不符)。保留第一個。
            d = df.loc[:, ~df.columns.duplicated()]
            t = d.reset_index()
            if "date" not in t.columns:
                t = t.rename(columns={t.columns[0]: "date"})
            date = pd.to_datetime(t["date"], errors="coerce")
            if getattr(date.dt, "tz", None) is not None:
                date = date.dt.tz_localize(None)
            date = date.astype("datetime64[ns]")  # 統一 ns (詳見 _norm_dt_index)
            if not set(_OHLC).issubset(t.columns):
                raise RuntimeError(f"缺 OHLC 欄: {list(t.columns)}")
            # 逐欄重建成乾淨的一維 numpy 陣列, 確保每個 frame 結構/維度一致,
            # 任何畸形欄都被攤平, concat 永遠不會吃到 2-D block。
            out = {"date": date.to_numpy()}
            for col in _OHLC:
                vals = t[col]
                if isinstance(vals, pd.DataFrame):  # 仍有重複 -> 取第一欄
                    vals = vals.iloc[:, 0]
                out[col] = pd.to_numeric(vals, errors="coerce").to_numpy()
            frame = pd.DataFrame(out)
            frame["code"] = str(code)
            frames.append(frame)
        except Exception as err:  # noqa: BLE001
            print(f"[history] 快取序列化跳過 {code}: {err}")
    if not frames:
        return
    long = _concat_frames(frames)
    if long is None or long.empty:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    long.to_parquet(HISTORY_PARQUET, index=False)


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    """合併所有 frame; 整批失敗時改逐一併入並揪出/略過異常元兇。

    每個 frame 進來前已重建為相同欄序的矩形, 整批 concat 理論上不該失敗;
    但正式環境曾持續報 numpy 維度不符 (某檔形狀異常)。改成: 先試整批 (快),
    失敗才退回逐一併入 -> 只略過真正壞掉的那一檔, 其餘照常寫入 (避免整份快取
    寫不進去 -> 每天重抓全市場), 並印出元兇的 shape/dtypes 供根因定位。
    """
    try:
        return pd.concat(frames, ignore_index=True)
    except Exception as err:  # noqa: BLE001
        print(f"[history] 整批 concat 失敗, 改逐一併入定位元兇: {err}")
    good: list[pd.DataFrame] = []
    for fr in frames:
        try:
            pd.concat([*good, fr], ignore_index=True)
            good.append(fr)
        except Exception as err:  # noqa: BLE001
            code = fr["code"].iloc[0] if "code" in fr and len(fr) else "?"
            print(f"[history] 略過異常 frame code={code} shape={fr.shape} "
                  f"cols={list(fr.columns)} dtypes={fr.dtypes.to_dict()}: {err}")
    if not good:
        return None
    return pd.concat(good, ignore_index=True)


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
    # 統一索引解析度 (us 快取 vs ns 新抓), 否則 concat 會炸 numpy 維度錯。
    old = old.copy()
    old.index = _norm_dt_index(old.index)
    new = new.copy()
    new.index = _norm_dt_index(new.index)
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

    # yfinance 仍抓不到的, 用 FinMind 備援 (需 FINMIND_TOKEN)
    still_missing = [(c, m) for c, m in codes_markets if c not in cache]
    if still_missing and finmind.available():
        print(f"[history] yfinance 缺 {len(still_missing)} 檔, 改用 FinMind 還原月K...")
        sess = make_session()
        got = 0
        for code, _market in still_missing:
            mdf = finmind.monthly_adjusted(code, sess)
            if mdf is not None and not mdf.empty:
                cache[code] = mdf
                got += 1
        print(f"[history] FinMind 補回 {got} 檔")

    if missing or stale or (still_missing and finmind.available()):
        try:
            _save_cache(cache)
        except Exception as err:  # noqa: BLE001
            # 快取只是加速用; 寫入失敗不該中斷當日選股與部署。
            print(f"[history] 快取寫入失敗 (不影響本次選股): {err}")

    return {c: cache[c] for c in sym_to_code.values() if c in cache}


# ---------- 近日原始日K (算漲停) ----------

def get_recent_daily(codes_markets: list[tuple[str, str]],
                     period: str = "2mo") -> dict[str, pd.DataFrame]:
    """近日原始(未還原)日K, 用來判斷漲停。回傳 {code: daily OHLC}。"""
    sym_to_code = {yf_symbol(c, m): c for c, m in codes_markets}
    raw = _download(list(sym_to_code), interval="1d", period=period,
                    auto_adjust=False)
    out = {sym_to_code[s]: df for s, df in raw.items()}

    # yfinance 抓不到的, 用 FinMind 備援
    missing = [(c, m) for c, m in codes_markets if c not in out]
    if missing and finmind.available():
        sess = make_session()
        for code, _market in missing:
            d = finmind.recent_daily_raw(code, sess)
            if d is not None and not d.empty:
                out[code] = d
    return out
