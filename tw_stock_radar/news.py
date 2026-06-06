"""今日國際重點:抓真實即時新聞(Google News RSS)→ AI 篩選/翻譯/濃縮。

聚焦『川普(Trump)的發言/決策』與『大型企業 CEO 的發言/決策』,排除分析師評論與例行行情。

新鮮度保證:
  1. RSS 查詢用 `when:1d`/`when:2d`(來源端時間過濾)。
  2. 依 pubDate 再過濾近 N 小時。
  3. AI 只從抓到的標題挑選與摘要,回傳索引,由本模組對回『真實來源連結』(AI 不產生網址)。

任何失敗(抓取/解析/AI)一律 graceful 回空,報表照常產出。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from . import ai
from .util import USER_AGENT

RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

_SYSTEM = (
    "你是專業的國際財經編輯。你會拿到一批『過去一兩天的真實新聞標題』(含來源)。\n"
    "請只挑出兩類、且真正可能帶動未來趨勢的重點:\n"
    "  (1) 川普(Trump)的發言、政策或決策;\n"
    "  (2) 大型企業 CEO 的發言、決策或重大宣布。\n"
    "嚴格排除:分析師/券商評論與目標價、單純股價漲跌、財經名嘴觀點、與上述兩類無關的新聞。\n"
    "規則:只能根據『提供的標題』,絕對不可自行添加未出現在清單中的事件或數字。"
    "若某則拿不準是不是當事人親口說/親自做的,寧可不選。\n"
    "用繁體中文,簡短精準。只回傳 JSON,不要多餘文字。"
)


def _rel_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    secs = (now - dt.astimezone(timezone.utc)).total_seconds()
    if secs < 0:
        return "剛剛"
    hours = int(secs // 3600)
    if hours < 1:
        return f"{int(secs // 60)} 分鐘前"
    if hours < 24:
        return f"{hours} 小時前"
    return f"{hours // 24} 天前"


def _parse_feed(xml_text: str) -> list[dict]:
    out: list[dict] = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src_el = item.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        pub_raw = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub_raw) if pub_raw else None
        except Exception:  # noqa: BLE001
            published = None
        out.append({"title": title, "link": link,
                    "source": source, "published": published})
    return out


def fetch_headlines(session: requests.Session | None, queries: list[str],
                    hours: int, cap: int) -> list[dict]:
    """抓多組 RSS 查詢、過濾近 `hours` 小時、去重,回傳最多 `cap` 則(新到舊)。"""
    sess = session or requests.Session()
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    items: list[dict] = []
    for q in queries:
        url = RSS.format(q=quote(q))
        try:
            resp = sess.get(url, timeout=20,
                            headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            feed = _parse_feed(resp.text)
        except Exception as err:  # noqa: BLE001
            print(f"[news] RSS 抓取失敗, 略過此查詢 ({q}): {err}")
            continue
        for it in feed:
            pub = it["published"]
            if pub is not None:
                age_h = (now - pub.astimezone(timezone.utc)).total_seconds() / 3600
                if age_h > hours:
                    continue
            key = it["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
    items.sort(key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc),
               reverse=True)
    return items[:cap]


def summarize(headlines: list[dict], max_display: int = 5) -> tuple[list[dict], str]:
    """AI 篩選/摘要,回 (items, takeaway)。items 連結用我方真實 URL。"""
    if not headlines:
        return [], ""
    client, model = ai.make_client()
    if client is None:
        print("[news] 未設定 AI 金鑰, 略過國際重點摘要。")
        return [], ""

    listing = "\n".join(
        f"[{i}] {h['title']}" + (f" ({h['source']})" if h["source"] else "")
        for i, h in enumerate(headlines)
    )
    user = (
        "以下是過去一兩天的真實新聞標題(每則前面是編號):\n" + listing + "\n\n"
        f"請挑出最多 {max_display} 則最重要的(川普 或 企業CEO 的發言/決策),"
        "依重要性排序,只回傳 JSON,格式如下:\n"
        '{"takeaway": "一句話總結今天國際最關鍵的訊號", '
        '"items": [{"idx": 0, "who": "川普 或 某CEO(公司)", '
        '"summary": "一句繁體中文重點(他說/做了什麼)", '
        '"why": "為何重要、對未來趨勢的意義(簡短)"}]}\n'
        "idx 必須是上面清單中的編號。若清單中沒有符合的重點, items 回空陣列。"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=2048,
        )
        data = ai.extract_json(resp.choices[0].message.content or "")
    except Exception as err:  # noqa: BLE001
        print(f"[news] AI 摘要失敗, 略過: {err}")
        return [], ""

    items: list[dict] = []
    for s in data.get("items", []):
        try:
            idx = int(s.get("idx", -1))
        except (TypeError, ValueError):
            idx = -1
        if not (0 <= idx < len(headlines)):
            continue  # 索引非法 -> 視為杜撰, 丟棄
        src = headlines[idx]
        summary = str(s.get("summary", "")).strip()
        if not summary:
            continue
        items.append({
            "who": str(s.get("who", "")).strip(),
            "summary": summary,
            "why": str(s.get("why", "")).strip(),
            "source": src["source"],
            "link": src["link"],
            "time": _rel_time(src["published"]),
        })
        if len(items) >= max_display:
            break
    takeaway = str(data.get("takeaway", "")).strip()
    print(f"[news] AI 已整理 {len(items)} 則國際重點 (model={model})。")
    return items, takeaway
