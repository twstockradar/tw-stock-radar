"""抓取當日全市場行情 (上市 TWSE + 上櫃 TPEX)。

回傳欄位: code, name, market, close, change, change_pct, trade_value,
trade_volume, next_limit_up (上櫃才有)。

上市改用 TWSE 盤後行情 MI_INDEX (收盤後即時更新); 舊的 STOCK_DAY_ALL OpenAPI
更新常延遲到晚間, 會導致顯示前一日的上市價格。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .util import get_json, make_session, roc_to_date, to_float

# 上市: 盤後即時行情 (每日收盤行情 - 全部, 不含權證等 0999)
TWSE_MI_INDEX = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
# 上櫃: TPEX OpenAPI (本身即時)
TPEX_DAILY = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

_TPE = timezone(timedelta(hours=8))


def _change_pct(close: float, change: float) -> float:
    """由收盤價與漲跌價差推算漲跌幅 (%)。"""
    prev = close - change
    if not prev or pd.isna(prev) or prev <= 0:
        return float("nan")
    return change / prev * 100.0


def _signed_change(dir_html, magnitude: float) -> float:
    """MI_INDEX 的漲跌『方向』在 HTML 欄 (綠=跌/紅=漲), 幅度在另一欄。"""
    if magnitude is None or pd.isna(magnitude):
        return float("nan")
    s = str(dir_html)
    if "green" in s or "-" in s:
        return -abs(magnitude)
    if "red" in s or "+" in s:
        return abs(magnitude)
    return 0.0  # 平盤


def _mi_index_table(payload: dict) -> tuple[list, dict]:
    """從 MI_INDEX 回應找出『全部證券收盤行情』那張表, 回 (rows, 欄位索引)。"""
    tables = payload.get("tables") or []
    # 舊格式相容: data1..data9 + fields1..fields9
    if not tables:
        for k in range(9, 0, -1):
            if payload.get(f"data{k}") and payload.get(f"fields{k}"):
                tables.append({"fields": payload[f"fields{k}"], "data": payload[f"data{k}"]})
    for t in tables:
        fields = t.get("fields") or []
        idx: dict[str, int] = {}
        for i, f in enumerate(fields):
            f = str(f)
            if "證券代號" in f:
                idx["code"] = i
            elif "證券名稱" in f:
                idx["name"] = i
            elif "成交股數" in f:
                idx["vol"] = i
            elif "成交金額" in f:
                idx["val"] = i
            elif f.strip() == "收盤價":
                idx["close"] = i
            elif "+/-" in f:
                idx["dir"] = i
            elif "價差" in f:
                idx["chg"] = i
        if {"code", "close", "chg"} <= idx.keys():
            return t.get("data") or [], idx
    return [], {}


def fetch_twse_daily(session=None) -> pd.DataFrame:
    """上市: MI_INDEX 盤後行情; 從今天往前找最近一個有資料的交易日 (處理假日)。"""
    sess = session or make_session()
    today = datetime.now(_TPE).date()
    for back in range(0, 8):
        d = today - timedelta(days=back)
        url = f"{TWSE_MI_INDEX}?date={d:%Y%m%d}&type=ALLBUT0999&response=json"
        try:
            payload = get_json(url, sess)
        except Exception as err:  # noqa: BLE001
            print(f"[daily_quotes] TWSE MI_INDEX {d:%Y%m%d} 取得失敗: {err}")
            continue
        if str(payload.get("stat")) != "OK":
            continue
        data, idx = _mi_index_table(payload)
        if not data:
            continue
        date = roc_to_date(payload.get("date")) if not payload.get("date", "").isdigit() \
            else pd.Timestamp(payload["date"])
        if pd.isna(date):
            date = pd.Timestamp(d)
        rows = []
        for r in data:
            try:
                close = to_float(r[idx["close"]])
                change = _signed_change(r[idx["dir"]] if "dir" in idx else "",
                                        to_float(r[idx["chg"]]))
                rows.append({
                    "code": str(r[idx["code"]]).strip(),
                    "name": str(r[idx["name"]]).strip() if "name" in idx else "",
                    "market": "TWSE",
                    "date": date,
                    "close": close,
                    "change": change,
                    "change_pct": _change_pct(close, change),
                    "trade_value": to_float(r[idx["val"]]) if "val" in idx else float("nan"),
                    "trade_volume": to_float(r[idx["vol"]]) if "vol" in idx else float("nan"),
                    "next_limit_up": float("nan"),
                })
            except (IndexError, KeyError):
                continue
        if rows:
            print(f"[daily_quotes] TWSE 上市 {date:%Y-%m-%d} {len(rows)} 檔 (MI_INDEX)")
            return pd.DataFrame(rows)
    raise RuntimeError("TWSE MI_INDEX 無法取得任何交易日資料")


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
    """合併上市+上櫃當日行情。只保留有有效收盤價的個股。

    防呆: 以『上市的交易日』為基準, 只保留同一交易日的資料, 避免某交易所
    資料延遲時混入前一日價格、卻被標成今天 (日期不一致 bug)。
    """
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

    # 日期一致性防呆: 以上市最新交易日為準, 丟掉非該日的資料 (避免混日期)。
    twse_dates = df.loc[df["market"] == "TWSE", "date"].dropna()
    if not twse_dates.empty:
        target = twse_dates.max()
        before = len(df)
        df = df[df["date"] == target].reset_index(drop=True)
        dropped = before - len(df)
        if dropped:
            print(f"[daily_quotes] 日期一致性: 以上市 {target:%Y-%m-%d} 為準, "
                  f"丟棄 {dropped} 筆不同日期資料")
    return df
