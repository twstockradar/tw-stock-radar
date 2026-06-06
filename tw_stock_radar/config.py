"""集中設定:路徑、門檻、狀態定義。使用者之後可在這裡調整篩選參數。"""
from __future__ import annotations

from pathlib import Path

# --- 路徑 ---
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
HISTORY_PARQUET = DATA_DIR / "monthly_history.parquet"

# --- 流動性過濾 ---
# 當日成交金額 (NTD) 低於此值視為冷門股, 不納入掃描。
LIQUIDITY_MIN_TRADE_VALUE = 5_000_000_000  # 50 億

# --- 月K 歷史新高 狀態分級 (用還原權值月K) ---
# dist = 最新還原收盤 / 歷史最高月High - 1
NEW_HIGH_TOLERANCE = 0.005    # dist >= -0.5%  => 創新高 (等於/突破歷史新高)
NEAR_HIGH_FLOOR = -0.10       # -10% <= dist < -0.5%  => 逼近新高
PULLBACK_FLOOR = -0.15        # dist >= -15% 且 前高在近 N 月內 => 高檔修正
PULLBACK_RECENT_MONTHS = 3
TREND_MA_MONTHS = 12          # 趨勢健全度: 最新收盤需 >= 自身 12 月均線

# --- 月K 縮圖 ---
CHART_MONTHS = 36             # 月K圖顯示最近幾個月

# --- 漲停 ---
LIMIT_UP_PCT = 9.8            # 近似漲停門檻 (單日收盤漲跌幅 %)
LIMIT_UP_LOOKBACK = 5         # 回看交易日數

# --- 資料充分性 ---
MIN_HISTORY_MONTHS = 18      # 月K至少幾根才納入評估 (避免新股雜訊)

# --- AI 族群/題材分類 ---
# 設定在 themes.py / 環境變數 (AI_API_KEY, AI_BASE_URL, AI_MODEL);
# 預設用 GitHub Models 的 openai/gpt-4o-mini, 可隨時切換其他 OpenAI 相容服務。

# --- 狀態定義 ---
STATUS_NEW_HIGH = "NEW_HIGH"
STATUS_NEAR_HIGH = "NEAR_HIGH"
STATUS_PULLBACK = "PULLBACK"
STATUS_ORDER = [STATUS_NEW_HIGH, STATUS_NEAR_HIGH, STATUS_PULLBACK]
STATUS_LABEL = {
    STATUS_NEW_HIGH: "創新高",
    STATUS_NEAR_HIGH: "逼近新高",
    STATUS_PULLBACK: "高檔修正",
}
STATUS_EMOJI = {
    STATUS_NEW_HIGH: "🔴",
    STATUS_NEAR_HIGH: "🟠",
    STATUS_PULLBACK: "🟡",
}
