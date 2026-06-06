"""共用的 AI(OpenAI 相容)存取層。

themes.py(族群分類)與 news.py(國際重點)共用這裡的金鑰讀取、用戶端建立與 JSON 解析。
預設走 GitHub Models(免費),可用環境變數切換到 Groq / OpenRouter / OpenAI:
  AI_API_KEY   金鑰(GitHub Models 用具 Models:read 的 GitHub token;
               也會自動讀 GITHUB_MODELS_TOKEN / GITHUB_TOKEN)。
  AI_BASE_URL  端點,預設 GitHub Models。
  AI_MODEL     模型,預設 openai/gpt-4.1。
"""
from __future__ import annotations

import json
import os

DEFAULT_BASE_URL = "https://models.github.ai/inference"
DEFAULT_MODEL = "openai/gpt-4.1"


def get_key() -> str | None:
    for name in ("AI_API_KEY", "GITHUB_MODELS_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(name)
        if val:
            return val
    return None


def make_client():
    """回傳 (client, model);無金鑰或缺套件時回 (None, model)。"""
    model = os.environ.get("AI_MODEL", DEFAULT_MODEL)
    key = get_key()
    if not key:
        return None, model
    try:
        from openai import OpenAI
    except Exception:  # noqa: BLE001
        return None, model
    base_url = os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(base_url=base_url, api_key=key), model


def extract_json(content: str) -> dict:
    """從模型回覆中取出 JSON 物件(容忍 markdown 圍欄與多餘文字)。"""
    if not content:
        return {}
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        return json.loads(content[start:end + 1])
    except Exception:  # noqa: BLE001
        return {}
