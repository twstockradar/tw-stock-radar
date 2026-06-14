"""產出 docs/index.html (今日) 與 docs/history/ (歷史封存頁)。

單一表格、依成交金額排序; 今日頁含月K圖與『今日新增』徽章, 封存頁不含圖。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import archive
from .config import DOCS_DIR, LIQUIDITY_MIN_TRADE_VALUE
from .util import format_amount

TEMPLATES_DIR = Path(__file__).parent / "templates"
_TPE = timezone(timedelta(hours=8))


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _now() -> str:
    return datetime.now(_TPE).strftime("%Y-%m-%d %H:%M")


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def _format_row(rec: dict, *, new_today: bool = False) -> dict:
    change = _num(rec.get("change_pct"))
    change = float(change) if change is not None else None
    close = _num(rec.get("close"))
    tv = _num(rec.get("trade_value"))
    mc = _num(rec.get("market_cap"))
    return {
        "code": rec.get("code", ""),
        "name": rec.get("name", ""),
        "group": rec.get("group") or "",
        "theme": rec.get("theme") or "",
        "close": f"{float(close):.2f}" if close is not None else "—",
        "change": change if change is not None else 0.0,
        "change_str": f"{change:+.2f}%" if change is not None else "—",
        "up": (change or 0.0) >= 0,
        "trade_value": float(tv) if tv is not None else 0.0,
        "trade_value_str": format_amount(tv),
        "market_cap": float(mc) if mc is not None else 0.0,
        "market_cap_str": format_amount(mc),
        "limit_up": bool(rec.get("limit_up")),
        "limit_up_count": int(_num(rec.get("limit_up_count")) or 0),
        "chart": rec.get("chart", "") or "",
        "new_today": bool(new_today),
    }


def _rows(records: list[dict], new_codes: set[str]) -> list[dict]:
    rows = [_format_row(r, new_today=(r.get("code") in new_codes)) for r in records]
    rows.sort(key=lambda x: x["trade_value"], reverse=True)
    return rows


def _group_counts(rows: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for r in rows:
        if r.get("group"):
            counts[r["group"]] = counts.get(r["group"], 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"name": g, "count": n} for g, n in ordered]


def _render_page(rows, *, data_date, total_scanned, focus, new_count,
                 show_charts, is_today, home_link, history_link, out_path,
                 news_items=None, news_takeaway="", stale_days=0) -> Path:
    html = _env().get_template("index.html.j2").render(
        rows=rows,
        total_scanned=total_scanned,
        total_hits=len(rows),
        data_date=data_date,
        update_time=_now(),
        liquidity_str=format_amount(LIQUIDITY_MIN_TRADE_VALUE),
        focus=focus,
        group_counts=_group_counts(rows),
        new_count=new_count,
        show_charts=show_charts,
        is_today=is_today,
        home_link=home_link,
        history_link=history_link,
        news_items=news_items or [],
        news_takeaway=news_takeaway or "",
        stale_days=stale_days,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def render_report(df: pd.DataFrame, *, data_date: str, total_scanned: int,
                  focus: str = "", new_codes: set[str] | None = None,
                  news_items: list[dict] | None = None, news_takeaway: str = "",
                  out_path: Path | None = None) -> Path:
    new_codes = new_codes or set()
    records = df.to_dict("records") if not df.empty else []
    rows = _rows(records, new_codes)
    try:
        dd = datetime.strptime(data_date, "%Y-%m-%d").date()
        stale_days = (datetime.now(_TPE).date() - dd).days
    except ValueError:
        stale_days = 0
    return _render_page(
        rows, data_date=data_date, total_scanned=total_scanned, focus=focus,
        new_count=sum(1 for r in rows if r["new_today"]),
        show_charts=True, is_today=True, home_link="", history_link="history/index.html",
        out_path=out_path or (DOCS_DIR / "index.html"),
        news_items=news_items, news_takeaway=news_takeaway, stale_days=stale_days,
    )


def build_history_site(out_dir: Path | None = None) -> None:
    """由 archive/*.json 產生 docs/history/ 索引頁 + 每日封存頁 (不含月K圖)。"""
    out_dir = out_dir or (DOCS_DIR / "history")
    out_dir.mkdir(parents=True, exist_ok=True)
    metas = []
    for d in archive.list_dates():
        snap = archive.load_snapshot(d)
        if not snap:
            continue
        new_codes = archive.new_codes_for(d)
        rows = _rows(snap.get("stocks", []), new_codes)
        snap_news = snap.get("news", {}) or {}
        _render_page(
            rows, data_date=d, total_scanned=None, focus=snap.get("focus", ""),
            new_count=len(new_codes), show_charts=False, is_today=False,
            home_link="../index.html", history_link="index.html",
            out_path=out_dir / f"{d}.html",
            news_items=snap_news.get("items", []),
            news_takeaway=snap_news.get("takeaway", ""),
        )
        metas.append({"date": d, "count": snap.get("count", len(rows)),
                      "new_count": len(new_codes), "focus": snap.get("focus", "")})
    metas.sort(key=lambda m: m["date"], reverse=True)
    html = _env().get_template("history.html.j2").render(items=metas, update_time=_now())
    (out_dir / "index.html").write_text(html, encoding="utf-8")
