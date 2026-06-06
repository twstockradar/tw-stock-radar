"""用 GitHub Models 自動把當日清單分成『族群/題材』, 並產生今日焦點摘要。

採 OpenAI 相容介面, 可用環境變數隨時切換服務 (GitHub Models / Groq / OpenRouter / OpenAI):
  AI_API_KEY   金鑰。GitHub Models 用 GitHub token(具 Models:read);
               也會自動讀 GITHUB_MODELS_TOKEN / GITHUB_TOKEN。
  AI_BASE_URL  端點, 預設 GitHub Models。
  AI_MODEL     模型, 預設 openai/gpt-4o-mini。

未設定金鑰或呼叫失敗時 graceful 回傳空結果, 報表照常產出, 不中斷每日流程。
"""
from __future__ import annotations

from . import ai

_SYSTEM = (
    "你是專業的台股產業分析師。你會拿到一份『月K創歷史新高 / 高檔』的台股清單, "
    "請把每一檔分類到 group(族群) 與 theme(題材):\n"
    "- group 用精準的當紅族群, 例如: 半導體、AI伺服器、PCB/CCL、散熱、電源/重電、"
    "光通訊CPO、記憶體、被動元件、機構件、網通、金融、航運。"
    "避免用『電腦』『電子』『其他』這類太籠統的詞; "
    "伺服器代工或品牌(如廣達、緯創、緯穎、技嘉、鴻海)請歸到『AI伺服器』。\n"
    "- theme 要具體, 例如: CoWoS先進封裝、ABF載板、AI伺服器代工、矽光子、HBM、"
    "重電、探針卡、伺服器滑軌、散熱模組 等。\n"
    "用繁體中文, 簡短精準(族群 2-6 字, 題材 2-10 字)。只回傳 JSON, 不要多餘文字。"
)


def classify_themes(stocks: list[dict]) -> tuple[dict[str, dict], str]:
    """stocks: [{'code','name'}, ...]。

    回傳 (mapping, focus):
      mapping = {code: {'group': 族群, 'theme': 題材}}
      focus   = 今日族群焦點 (一兩句話)
    """
    if not stocks:
        return {}, ""
    client, model = ai.make_client()
    if client is None:
        print("[themes] 未設定 AI 金鑰 (AI_API_KEY / GITHUB_TOKEN), 略過 AI 族群分類。")
        return {}, ""

    listing = "\n".join(f"{s['code']} {s['name']}" for s in stocks)
    user = (
        "以下是今天的清單 (代碼 股名):\n" + listing + "\n\n"
        "請逐檔分類, 只回傳 JSON, 格式如下(每一檔都要出現, code 用原始代碼字串):\n"
        '{"focus": "一兩句話總結這份清單目前以哪些族群/題材為主", '
        '"stocks": [{"code": "2330", "group": "半導體", "theme": "晶圓代工"}]}'
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096,
        )
        data = ai.extract_json(resp.choices[0].message.content or "")
        mapping = {}
        for s in data.get("stocks", []):
            code = str(s.get("code", "")).strip()
            if code:
                mapping[code] = {
                    "group": str(s.get("group", "")).strip(),
                    "theme": str(s.get("theme", "")).strip(),
                }
        focus = str(data.get("focus", "")).strip()
        print(f"[themes] AI 已分類 {len(mapping)} 檔 (model={model})。")
        return mapping, focus
    except Exception as err:  # noqa: BLE001
        print(f"[themes] AI 分類失敗, 略過: {err}")
        return {}, ""
