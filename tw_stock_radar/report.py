"""產出自包含的 docs/index.html (Jinja2)。

單一表格 (不分區塊), 預設依成交金額由大到小排序; 表頭可點擊重新排序。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import DOCS_DIR, LIQUIDITY_MIN_TRADE_VALUE
from .util import format_amount

TEMPLATES_DIR = Path(__file__).parent / "templates"
_TPE = timezone(timedelta(hours=8))


def _row_to_dict(r) -> dict:
    change = float(r.change_pct) if pd.notna(r.change_pct) else None
    return {
        "code": r.code,
        "name": r.name,
        "group": "" if pd.isna(getattr(r, "group", "")) else str(getattr(r, "group", "")),
        "theme": "" if pd.isna(getattr(r, "theme", "")) else str(getattr(r, "theme", "")),
        "close": f"{float(r.close):.2f}",
        "change": change if change is not None else 0.0,
        "change_str": f"{change:+.2f}%" if change is not None else "—",
        "up": (change or 0.0) >= 0,
        "trade_value": float(r.trade_value) if pd.notna(r.trade_value) else 0.0,
        "trade_value_str": format_amount(r.trade_value),
        "market_cap": float(r.market_cap) if pd.notna(r.market_cap) else 0.0,
        "market_cap_str": format_amount(r.market_cap),
        "limit_up": bool(r.limit_up),
        "limit_up_count": int(r.limit_up_count),
        "chart": r.chart,
    }


def build_rows(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    d = df.sort_values("trade_value", ascending=False)
    return [_row_to_dict(r) for r in d.itertuples(index=False)]


def _group_counts(rows: list[dict]) -> list[dict]:
    """統計各族群檔數, 由多到少。"""
    counts: dict[str, int] = {}
    for r in rows:
        g = r.get("group", "")
        if g:
            counts[g] = counts.get(g, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"name": g, "count": n} for g, n in ordered]


def render_report(df: pd.DataFrame, *, data_date: str, total_scanned: int,
                  focus: str = "", out_path: Path | None = None) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("index.html.j2")
    rows = build_rows(df)
    html = template.render(
        rows=rows,
        total_scanned=total_scanned,
        total_hits=int(len(df)),
        data_date=data_date,
        update_time=datetime.now(_TPE).strftime("%Y-%m-%d %H:%M"),
        liquidity_str=format_amount(LIQUIDITY_MIN_TRADE_VALUE),
        focus=focus,
        group_counts=_group_counts(rows),
    )
    out = out_path or (DOCS_DIR / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
