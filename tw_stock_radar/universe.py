"""建立掃描宇宙: 上市+上櫃普通股, 附發行股數與產業。

關鍵作法: 直接用「公司基本資料」當宇宙來源。基本資料本身只含「公司」,
ETF/受益憑證/權證不在其中 -> 自動排除 ETF; KY 公司有基本資料 -> 自動保留。
特別股(如 2887A)在基本資料無對應代號 -> join 後自然被排除。

市值 = 收盤價 x 已發行股數。
"""
from __future__ import annotations

import pandas as pd

from .util import get_json, to_float

TWSE_BASIC = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_BASIC = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

# 防呆: 萬一有非普通股漏進來, 用名稱關鍵字再擋一層。
_EXCLUDE_NAME_KEYWORDS = ("ETF", "ETN", "基金", "受益", "購", "售")


def fetch_twse_basic(session=None) -> pd.DataFrame:
    data = get_json(TWSE_BASIC, session)
    rows = []
    for r in data:
        rows.append({
            "code": str(r.get("公司代號", "")).strip(),
            "shares": to_float(r.get("已發行普通股數或TDR原股發行股數")),
            "industry": str(r.get("產業別", "")).strip(),
        })
    return pd.DataFrame(rows)


def fetch_tpex_basic(session=None) -> pd.DataFrame:
    data = get_json(TPEX_BASIC, session)
    rows = []
    for r in data:
        rows.append({
            "code": str(r.get("SecuritiesCompanyCode", "")).strip(),
            "shares": to_float(r.get("IssueShares")),
            "industry": str(r.get("SecuritiesIndustryCode", "")).strip(),
        })
    return pd.DataFrame(rows)


def fetch_basic_info(session=None) -> pd.DataFrame:
    """合併上市+上櫃公司基本資料 (code, shares, industry)。"""
    frames = []
    for fetch in (fetch_twse_basic, fetch_tpex_basic):
        try:
            frames.append(fetch(session))
        except Exception as err:  # noqa: BLE001
            print(f"[universe] 警告: {fetch.__name__} 失敗: {err}")
    if not frames:
        raise RuntimeError("無法取得公司基本資料")
    basic = pd.concat(frames, ignore_index=True)
    basic = basic[basic["code"].str.match(r"^\d{4,6}$", na=False)]
    basic = basic.drop_duplicates("code").reset_index(drop=True)
    return basic


def build_universe(quotes: pd.DataFrame, basic: pd.DataFrame) -> pd.DataFrame:
    """以「有公司基本資料」者為宇宙, 內接當日行情, 計算市值。"""
    df = quotes.merge(basic, on="code", how="inner")
    # 名稱關鍵字防呆 (基本資料理論上已排除, 這層是保險)
    mask = ~df["name"].str.contains("|".join(_EXCLUDE_NAME_KEYWORDS), na=False)
    df = df[mask].copy()
    df["market_cap"] = df["close"] * df["shares"]
    return df.reset_index(drop=True)
