"""月K縮圖: mplfinance 畫還原月K蠟燭圖 -> base64 data URI (內嵌 HTML)。

台股慣例: 紅漲綠跌。標一條歷史新高水平線。
"""
from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")  # 無視窗環境 (CI) 必須
import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402

from .config import CHART_MONTHS  # noqa: E402

_MARKET_COLORS = mpf.make_marketcolors(
    up="#e2342d", down="#11a675", edge="inherit", wick="inherit",
)
_STYLE = mpf.make_mpf_style(
    marketcolors=_MARKET_COLORS, facecolor="white",
    rc={"axes.edgecolor": "#e5e5e5"},
)


def monthly_chart_base64(monthly: pd.DataFrame | None, ath: float | None = None) -> str:
    """回傳 'data:image/png;base64,...' 字串; 失敗回空字串。"""
    if monthly is None or monthly.empty:
        return ""
    sub = monthly.tail(CHART_MONTHS)
    if sub.empty:
        return ""
    hlines = None
    if ath:
        hlines = {"hlines": [ath], "colors": ["#e2342d"],
                  "linestyle": "--", "linewidths": 0.7}
    fig = None
    try:
        kwargs = {
            "type": "candle", "style": _STYLE, "volume": False,
            "figratio": (2.6, 1.4), "figscale": 0.5,
            "returnfig": True, "tight_layout": True, "scale_padding": 0.1,
        }
        if hlines:
            kwargs["hlines"] = hlines
        fig, axes = mpf.plot(sub, **kwargs)
        for ax in axes:
            ax.set_axis_off()
        buf = io.BytesIO()
        fig.savefig(buf, dpi=90, bbox_inches="tight", pad_inches=0.02)
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")
    except Exception as err:  # noqa: BLE001
        print(f"[charts] 繪圖失敗: {err}")
        return ""
    finally:
        if fig is not None:
            plt.close(fig)
