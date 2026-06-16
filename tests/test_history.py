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
