"""ai.py 共用層測試: 金鑰讀取優先序、JSON 容錯解析。"""
from tw_stock_radar import ai


def test_extract_json_plain():
    assert ai.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_markdown_fence():
    raw = "```json\n{\"focus\": \"x\", \"stocks\": []}\n```"
    assert ai.extract_json(raw) == {"focus": "x", "stocks": []}


def test_extract_json_with_surrounding_text():
    raw = "好的, 結果如下: {\"k\": [1, 2]} 以上。"
    assert ai.extract_json(raw) == {"k": [1, 2]}


def test_extract_json_garbage_returns_empty():
    assert ai.extract_json("沒有 JSON") == {}
    assert ai.extract_json("") == {}


def test_get_key_priority(monkeypatch):
    for n in ("AI_API_KEY", "GITHUB_MODELS_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(n, raising=False)
    assert ai.get_key() is None
    monkeypatch.setenv("GITHUB_TOKEN", "g")
    assert ai.get_key() == "g"
    monkeypatch.setenv("AI_API_KEY", "primary")
    assert ai.get_key() == "primary"
