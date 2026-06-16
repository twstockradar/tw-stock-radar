"""history.py 測試: _save_cache 對 tz-aware / 結構不一致的 frame 要穩健 (防 concat 崩潰)。"""
import pandas as pd

from tw_stock_radar import history


def _frame(periods, tz=None):
    idx = pd.date_range("2020-01-01", periods=periods, freq="MS", tz=tz)
    idx.name = "date"
    vals = list(range(periods))
    return pd.DataFrame({"Open": vals, "High": vals, "Low": vals, "Close": vals},
                        index=idx)


def test_save_cache_mixes_tz_aware_and_naive(tmp_path, monkeypatch):
    """混合 tz-aware 與 tz-naive、且長度不同的 frame 不該崩潰 (曾導致每日流程中斷)。"""
    parquet = tmp_path / "monthly_history.parquet"
    monkeypatch.setattr(history, "HISTORY_PARQUET", parquet)
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)

    cache = {
        "2330": _frame(318, tz=None),
        "2317": _frame(217, tz="Asia/Taipei"),  # 帶時區 + 長度不同
    }
    history._save_cache(cache)  # 不應丟出例外

    long = pd.read_parquet(parquet)
    assert set(long["code"]) == {"2330", "2317"}
    # 寫回後再讀, date 應為 tz-naive datetime
    assert long["date"].dt.tz is None


def _frame_unit(periods, unit, start="1995-01-01"):
    """指定 datetime 解析度 (us/ns) 的 frame, 模擬 parquet(us) vs yfinance(ns)。"""
    idx = pd.DatetimeIndex(
        pd.date_range(start, periods=periods, freq="MS").values.astype(f"datetime64[{unit}]"))
    idx.name = "date"
    vals = list(range(periods))
    return pd.DataFrame({"Open": vals, "High": vals, "Low": vals, "Close": vals},
                        index=idx)


def test_save_cache_mixes_us_and_ns_resolution(tmp_path, monkeypatch):
    """pyarrow 快取(us)與 yfinance 新抓(ns)混合不該崩潰 (正式環境真因)。"""
    parquet = tmp_path / "monthly_history.parquet"
    monkeypatch.setattr(history, "HISTORY_PARQUET", parquet)
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)

    # ≥6 個 us frame + 1 個 ns frame, 重現 concat numpy 維度錯
    cache = {str(1000 + i): _frame_unit(318 - i, "us") for i in range(6)}
    cache["2330"] = _frame_unit(217, "ns", start="2000-01-01")
    history._save_cache(cache)  # 不應丟出例外

    long = pd.read_parquet(parquet)
    assert long["code"].nunique() == 7  # 全部寫入, 一檔都沒被略過


def test_merge_tail_mixes_us_and_ns_resolution():
    """增量更新時 舊快取(us) + 新抓(ns) 合併不該崩潰 (此路徑無 try/except 保護)。"""
    old = _frame_unit(318, "us")
    new = _frame_unit(6, "ns", start="2021-06-01")
    merged = history._merge_tail(old, new)  # 不應丟出例外
    assert not merged.empty


def test_save_cache_handles_duplicate_columns(tmp_path, monkeypatch):
    """yfinance 偶發回傳重複 OHLC 欄時, 不該讓整批快取寫入崩潰 (正式環境真因)。"""
    parquet = tmp_path / "monthly_history.parquet"
    monkeypatch.setattr(history, "HISTORY_PARQUET", parquet)
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)

    dup = _frame(318)
    dup["extra"] = list(range(318))
    dup.columns = ["Open", "High", "Low", "Close", "Close"]  # 重複 Close 欄

    cache = {"2330": dup, "2317": _frame(217)}
    history._save_cache(cache)  # 不應丟出例外

    long = pd.read_parquet(parquet)
    assert set(long["code"]) == {"2330", "2317"}
    assert list(long.columns) == ["date", *history._OHLC, "code"]
