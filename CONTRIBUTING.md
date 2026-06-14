# 貢獻指南

歡迎一起改進台股月K雷達 🙌

## 開發環境

```powershell
python -m pip install -r requirements-dev.txt
```

## 快速測試 (不必掃全市場)

```powershell
# 指定幾檔
python -m tw_stock_radar --codes 2330,2454,3017

# 只取流動性前 N 檔
python -m tw_stock_radar --limit 80
```

輸出在 `docs/index.html`,用瀏覽器直接打開即可。

## 送 PR 前

```powershell
ruff check .     # 風格檢查
pytest -q        # 單元測試
```

CI 會跑同樣的檢查。新增邏輯請盡量補一個對應測試 (純函式優先,見 `tests/`)。

## 設計原則 / 範圍

- **每日流程絕不能因為單一功能失敗而中斷**:AI、新聞、FinMind 等選用功能一律「失敗則略過」,報表照常產出。新增外部相依時請沿用這個原則 (graceful degradation)。
- **顯示維持單一表格、依成交金額排序、不分區塊**:這是刻意的設計決定,請勿加回上市櫃分區或狀態標籤欄。
- **AI 不產生事實**:像今日國際重點那樣,AI 只負責挑選/翻譯/濃縮既有資料,連結等事實由程式對回真實來源,避免幻覺。
- 篩選門檻集中在 `tw_stock_radar/config.py`,調參數請改那裡。

## 回報問題

開 issue 時請附上:執行指令、完整錯誤訊息、Python 版本。資料源 (TWSE/TPEX/Yahoo) 偶有改版或限流,先說明是哪一步失敗會更好追。
