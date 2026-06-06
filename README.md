# 📈 TW\_STOCK\_RADAR — 台股月K創新高每日雷達

每天收盤後自動掃描台股(上市＋上櫃),用**還原權值月K**找出**趨勢向上、目前處於歷史高檔**的個股,
產生一頁可公開分享的網頁,並透過 GitHub Actions 每日自動更新與部署到 GitHub Pages。

> 用意:以「月K」當基準,挑出公司目前處於最好狀態(已創新高 / 逼近新高 / 高檔修正但仍在高位)的標的。

---

## 線上看

👉 **https://twstockradar.github.io/tw-stock-radar/**（每日台灣時間 16:00 自動更新）

## 表單欄位

| 欄位 | 說明 |
|------|------|
| 代碼 / 股名 | 個股代號與名稱 |
| 族群 · 題材 | 由 AI 自動分類(選用,預設 GitHub Models 免費 GPT),顯示於股名下方 |
| 價格 | 當日收盤價 |
| 漲跌幅 | 當日漲跌幅 %(紅漲綠跌) |
| 成交金額 | 當日成交值 |
| 市值 | 收盤價 × 已發行股數 |
| 近5日漲停 | 近 5 個交易日是否曾(收盤)漲停及次數 |
| 還原月K（36月） | 右側內嵌的還原權值月K縮圖(已還原配息配股) |

清單合併為**一張表**(不分區塊),**預設依成交金額由大到小排序**;表頭可點擊改排序、上方可搜尋代碼/股名。

---

## 快速開始(本機)

```powershell
# 1. 安裝套件
python -m pip install -r requirements.txt

# 2. 小範圍測試(指定代碼)
python -m tw_stock_radar --codes 2330,2454,3017,2317

# 3. 快速測試(只取流動性前 N 檔)
python -m tw_stock_radar --limit 80

# 4. 掃描全市場(正式)
python -m tw_stock_radar
```

輸出檔:`docs/index.html`(單一自包含檔案,月K圖以 base64 內嵌,直接用瀏覽器開啟即可)。
還原月K歷史會快取在 `data/monthly_history.parquet`,之後每日只增量更新近月。

### 指令參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `--limit N` | 0(不限) | 只取流動性前 N 檔,用於快速測試 |
| `--codes a,b,c` | 無 | 只掃描指定代碼(會忽略流動性門檻) |
| `--min-value` | 5000000000 | 成交金額流動性門檻(NTD) |

---

## 篩選邏輯(可在 `tw_stock_radar/config.py` 調整)

用還原月K計算 `dist = 最新還原收盤 / 歷史最高月High − 1`:

| 狀態 | 條件 |
|------|------|
| 🔴 創新高 | `dist ≥ −0.5%`(等於或突破歷史新高) |
| 🟠 逼近新高 | `−10% ≤ dist < −0.5%` |
| 🟡 高檔修正 | 前高在近 3 個月內 **且** `dist ≥ −15%` |

另要求:當日**成交金額 ≥ 門檻**(預設 50 億)、收盤**站上 12 月均線**、月K**至少 18 根**(濾掉新股雜訊)。

主要可調參數:`LIQUIDITY_MIN_TRADE_VALUE`、`NEW_HIGH_TOLERANCE`、`NEAR_HIGH_FLOOR`、`PULLBACK_FLOOR`、
`PULLBACK_RECENT_MONTHS`、`TREND_MA_MONTHS`、`MIN_HISTORY_MONTHS`、`CHART_MONTHS`、`LIMIT_UP_PCT`。

---

## AI 族群 / 題材分類（選用、免費）

預設用 **GitHub Models** 的 **`openai/gpt-4.1`**(免費)自動把當日清單分成
**族群 / 題材**(顆粒度可到 AI伺服器、CoWoS先進封裝、散熱、CCL、CPO光通訊…),顯示在每檔股名下方,
並在頁面頂部產生「**今日族群焦點**」摘要與**族群分布**統計。

- **未設定金鑰或呼叫失敗會自動略過**,報表照常產出,不影響每日流程。
- OpenAI 相容設計,用環境變數即可切換到 Groq / OpenRouter / OpenAI 等:
  `AI_API_KEY`(金鑰)、`AI_BASE_URL`(端點)、`AI_MODEL`(模型)。

**本機使用**:到 GitHub → Settings → Developer settings → Fine-grained tokens 開一支具 **Models: read** 權限的 token,再:

```powershell
$env:AI_API_KEY = "github_pat_..."   # 或設成 GITHUB_MODELS_TOKEN
python -m tw_stock_radar
```

**GitHub Actions**:
- **個人帳號 repo**:用內建 `GITHUB_TOKEN` + `permissions: models: read` 即可,**不需額外 secret**。
- **組織 repo(本專案)**:組織預設會擋內建 token 呼叫 Models(403),需到 repo
  **Settings → Secrets and variables → Actions** 新增 secret **`AI_API_KEY`**,值為一支
  **個人帳號**具 **Models: read** 的 fine-grained PAT;workflow 會優先讀它。未設則 AI 分類自動略過。

> 想換 Groq(範例):`$env:AI_BASE_URL="https://api.groq.com/openai/v1"; $env:AI_MODEL="llama-3.3-70b-versatile"; $env:AI_API_KEY="gsk_..."`

---

## 歷史封存 + 今日新增

每天的清單會存成 `archive/<日期>.json`(commit 回 repo 保存),網站據此產生:

- **🆕 今日新增**:今日榜上、但前一個交易日不在榜的個股,表格會標 🆕,上方顯示「今日新增 N」。
- **📅 歷史封存**:頁面上方「歷史封存」可瀏覽每一天的名單(封存頁為表格、不含月K圖)。網址 `…/history/`。

GitHub Actions 產生報表後會自動把當天 `archive/*.json` commit 回 repo(需 `permissions: contents: write`,已設定)。

---

## FinMind 備援(選用)

擔心雲端某天被 Yahoo 限流抓不到資料?設定 `FINMIND_TOKEN`(到 [finmindtrade.com](https://finmindtrade.com) 免費註冊取得),
yfinance 抓不到的個股會自動改用 **FinMind**(`TaiwanStockPriceAdj` 還原月K、`TaiwanStockPrice` 原始日K)。

- 沒設 token → 維持只用 yfinance(零風險)。
- GitHub Actions:**Settings → Secrets and variables → Actions** 新增 secret `FINMIND_TOKEN`,workflow 已會帶入。
- 本機:`$env:FINMIND_TOKEN = "..."`。

---

## 每日自動更新(GitHub Actions + Pages)

1. 把整個專案推上 GitHub。
2. Repo → **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。
3. 工作流程 [`.github/workflows/daily.yml`](.github/workflows/daily.yml) 會:
   - 每個交易日 **台灣時間 16:00**(08:00 UTC)自動執行,也可在 **Actions** 頁面手動 `Run workflow`。
   - 安裝套件 → `python -m tw_stock_radar` → 上傳 `docs/` → 部署到 Pages(**不** commit 回 repo,保持乾淨)。
   - 用 `actions/cache` 保存還原月K歷史,避免每天重抓全市場。

> 註:GitHub 排程以 UTC 計算且尖峰可能延遲;若需精準時間可改用自架 cron。

---

## 資料來源

- 上市每日行情:TWSE OpenAPI `exchangeReport/STOCK_DAY_ALL`
- 上櫃每日行情:TPEX OpenAPI `tpex_mainboard_daily_close_quotes`
- 上市/上櫃公司基本資料(發行股數、產業):TWSE `opendata/t187ap03_L`、TPEX `mopsfin_t187ap03_O`
- 還原權值月K與近日日K:Yahoo Finance(`yfinance`);備援:FinMind(選用,需 `FINMIND_TOKEN`)
- 族群 / 題材自動分類:GitHub Models(`openai/gpt-4.1`,免費、選用;OpenAI 相容、可切換)

公司基本資料本身只含「公司」,天生排除 ETF/受益憑證,KY 公司則保留 —— 因此宇宙自動符合「排 ETF、留 KY」。

---

## 之後可精進

- 歷史封存頁與「今日新增名單」追蹤、LINE/Telegram 推播
- 漲停改用升降單位精算(目前以收盤漲幅近似)
- 加入相對強弱、量能放大、法人買超等趨勢條件;產業分組
- 資料源加上 FinMind 作為備援以提升穩定度

---

## 免責聲明

本專案僅供研究與教育參考,不構成任何投資建議。資料可能有誤差或延遲,請以官方公告為準。
