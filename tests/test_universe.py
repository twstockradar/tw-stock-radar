"""universe.py 測試: 基本資料來源失敗時以快取補回 (防「只有五檔」殘缺宇宙)。"""
import pandas as pd
import pytest

from tw_stock_radar import universe


def _twse():
    return pd.DataFrame({"code": ["2330", "2317"],
                         "shares": [1.0, 2.0], "industry": ["半導體", "電子"]})


def _tpex():
    return pd.DataFrame({"code": ["3105"], "shares": [3.0], "industry": ["生技"]})


def test_basic_info_falls_back_to_cache_when_source_fails(tmp_path, monkeypatch):
    """TWSE 失敗時, 上市股應由快取補回, 而非整批消失。"""
    cache = tmp_path / "basic_info.parquet"
    monkeypatch.setattr(universe, "BASIC_CACHE", cache)
    monkeypatch.setattr(universe, "DATA_DIR", tmp_path)

    # 第一次兩來源都成功 -> 寫入快取
    monkeypatch.setattr(universe, "fetch_twse_basic", lambda s=None: _twse())
    monkeypatch.setattr(universe, "fetch_tpex_basic", lambda s=None: _tpex())
    full = universe.fetch_basic_info()
    assert set(full["code"]) == {"2330", "2317", "3105"}
    assert cache.exists()

    # 第二次 TWSE 掛掉 -> 上市股(2330/2317)應由快取補回
    def _boom(s=None):
        raise RuntimeError("API 掛掉")

    monkeypatch.setattr(universe, "fetch_twse_basic", _boom)
    degraded = universe.fetch_basic_info()
    assert set(degraded["code"]) == {"2330", "2317", "3105"}


def test_partial_failure_does_not_overwrite_cache(tmp_path, monkeypatch):
    """來源不完整時不可把殘缺資料寫回快取 (避免污染)。"""
    cache = tmp_path / "basic_info.parquet"
    monkeypatch.setattr(universe, "BASIC_CACHE", cache)
    monkeypatch.setattr(universe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(universe, "fetch_twse_basic", lambda s=None: _twse())
    monkeypatch.setattr(universe, "fetch_tpex_basic", lambda s=None: _tpex())
    universe.fetch_basic_info()  # 建立完整快取 (3 檔)

    def _boom(s=None):
        raise RuntimeError("API 掛掉")

    monkeypatch.setattr(universe, "fetch_tpex_basic", _boom)
    universe.fetch_basic_info()  # TPEX 失敗
    # 快取仍應是先前完整的 3 檔, 未被殘缺結果覆蓋
    assert len(pd.read_parquet(cache)) == 3


def test_no_source_and_no_cache_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "BASIC_CACHE", tmp_path / "nope.parquet")
    monkeypatch.setattr(universe, "DATA_DIR", tmp_path)

    def _boom(s=None):
        raise RuntimeError("API 掛掉")

    monkeypatch.setattr(universe, "fetch_twse_basic", _boom)
    monkeypatch.setattr(universe, "fetch_tpex_basic", _boom)
    with pytest.raises(RuntimeError):
        universe.fetch_basic_info()
