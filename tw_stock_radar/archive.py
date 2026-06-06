"""每日結果封存 (JSON) 與『今日新增』比對。

archive/<YYYY-MM-DD>.json 會 commit 回 repo 以保存歷史;
docs/history/ 的網頁則每次由這些 JSON 重新產生 (artifact 部署, 不進版控)。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from .config import ROOT

ARCHIVE_DIR = ROOT / "archive"
_FIELDS = ["code", "name", "market", "close", "change_pct", "trade_value",
           "market_cap", "status", "dist", "limit_up", "limit_up_count",
           "group", "theme"]


def _clean(v):
    """轉成可 JSON 序列化的值; NaN -> None。"""
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def save_snapshot(cand: pd.DataFrame, data_date: str, focus: str = "") -> Path | None:
    """把當日清單寫成 archive/<date>.json (不含月K圖, 保持輕量)。"""
    if cand is None or cand.empty:
        return None
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cols = [c for c in _FIELDS if c in cand.columns]
    records = [{k: _clean(v) for k, v in rec.items()}
               for rec in cand[cols].to_dict("records")]
    payload = {"date": data_date, "count": len(records),
               "focus": focus or "", "stocks": records}
    path = ARCHIVE_DIR / f"{data_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=0),
                    encoding="utf-8")
    return path


def list_dates() -> list[str]:
    if not ARCHIVE_DIR.exists():
        return []
    return sorted(p.stem for p in ARCHIVE_DIR.glob("*.json"))


def load_snapshot(date: str) -> dict | None:
    path = ARCHIVE_DIR / f"{date}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _codes(snapshot: dict | None) -> set[str]:
    if not snapshot:
        return set()
    return {s.get("code") for s in snapshot.get("stocks", []) if s.get("code")}


def previous_codes(before_date: str) -> set[str]:
    """前一個封存日 (< before_date) 的代碼集合。"""
    earlier = [d for d in list_dates() if d < before_date]
    if not earlier:
        return set()
    return _codes(load_snapshot(earlier[-1]))


def new_codes_for(date: str) -> set[str]:
    """該封存日相對於前一個封存日的『新增』代碼。首日回空集合。"""
    prev = previous_codes(date)
    if not prev:
        return set()
    return _codes(load_snapshot(date)) - prev
