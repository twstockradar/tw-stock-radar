"""每日流程編排。

用法:
  python -m tw_stock_radar                 # 掃描全市場
  python -m tw_stock_radar --limit 80      # 只取流動性前 80 檔 (快速測試)
  python -m tw_stock_radar --codes 2330,2454,3017
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import archive
from .charts import monthly_chart_base64
from .config import LIQUIDITY_MIN_TRADE_VALUE
from .daily_quotes import fetch_daily_quotes
from .history import get_monthly_history, get_recent_daily
from .report import build_history_site, render_report
from .screen import compute_limit_up, evaluate_monthly
from .themes import classify_themes
from .universe import build_universe, fetch_basic_info
from .util import make_session

_TPE = timezone(timedelta(hours=8))
_RENDER_COLS = ["code", "name", "market", "close", "change_pct", "trade_value",
                "market_cap", "status", "dist", "limit_up", "limit_up_count",
                "chart", "group", "theme"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tw_stock_radar")
    p.add_argument("--limit", type=int, default=0,
                   help="只取流動性前 N 檔 (0=不限, 用於快速測試)")
    p.add_argument("--codes", type=str, default="",
                   help="只掃描指定代碼 (逗號分隔), 會忽略流動性門檻")
    p.add_argument("--min-value", type=float, default=float(LIQUIDITY_MIN_TRADE_VALUE),
                   help="成交金額流動性門檻 (NTD)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Windows 主控台預設 cp950 無法輸出部分符號, 強制 UTF-8 避免中斷。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    args = parse_args(argv if argv is not None else sys.argv[1:])
    t0 = time.time()
    session = make_session()

    print("→ 抓取當日行情 (TWSE + TPEX)...")
    quotes = fetch_daily_quotes(session)
    print(f"  當日有效行情 {len(quotes)} 檔")

    dd = pd.to_datetime(quotes["date"], errors="coerce").max()
    data_date = dd.strftime("%Y-%m-%d") if pd.notna(dd) \
        else datetime.now(_TPE).strftime("%Y-%m-%d")

    print("→ 抓取公司基本資料 (發行股數/產業)...")
    basic = fetch_basic_info(session)
    universe = build_universe(quotes, basic)
    print(f"  宇宙 (普通股, 排ETF/留KY) {len(universe)} 檔")

    # --- 選定要評估的個股 ---
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        liquid = universe[universe["code"].isin(wanted)].copy()
    else:
        liquid = universe[universe["trade_value"] >= args.min_value].copy()
        if args.limit and len(liquid) > args.limit:
            liquid = liquid.sort_values("trade_value", ascending=False).head(args.limit).copy()
    print(f"  待評估 {len(liquid)} 檔, 抓取還原月K歷史...")

    monthly = get_monthly_history(list(zip(liquid["code"], liquid["market"])))

    metrics = evaluate_monthly(liquid["code"].tolist(), monthly)
    print(f"  符合月K歷史新高狀態 {len(metrics)} 檔")

    focus = ""
    if metrics.empty:
        cand = pd.DataFrame(columns=_RENDER_COLS)
    else:
        cand = liquid.merge(metrics, on="code", how="inner")
        print("  抓取近日原始日K, 判斷漲停...")
        daily = get_recent_daily(list(zip(cand["code"], cand["market"])))
        cand = cand.merge(compute_limit_up(cand["code"].tolist(), daily),
                          on="code", how="left")
        cand["limit_up"] = cand["limit_up"].fillna(False)
        cand["limit_up_count"] = cand["limit_up_count"].fillna(0).astype(int)
        print("  繪製月K縮圖...")
        cand["chart"] = [monthly_chart_base64(monthly.get(c), a)
                         for c, a in zip(cand["code"], cand["ath"])]
        print("  AI 族群/題材分類...")
        themes_map, focus = classify_themes(cand[["code", "name"]].to_dict("records"))
        cand["group"] = cand["code"].map(lambda c: themes_map.get(c, {}).get("group", ""))
        cand["theme"] = cand["code"].map(lambda c: themes_map.get(c, {}).get("theme", ""))

    # 今日新增 (相對前一封存日) + 封存今日結果
    new_codes: set[str] = set()
    if not cand.empty:
        prev = archive.previous_codes(data_date)
        if prev:
            new_codes = set(cand["code"]) - prev
        archive.save_snapshot(cand, data_date, focus)

    out = render_report(cand, data_date=data_date, total_scanned=len(liquid),
                        focus=focus, new_codes=new_codes)
    build_history_site()
    print(f"✓ 完成 -> {out}  (耗時 {time.time() - t0:.0f}s, "
          f"符合 {len(cand)} 檔, 今日新增 {len(new_codes)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
