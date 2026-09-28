import os
import json
import random
from datetime import datetime, timedelta, timezone

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
STATE_PATH = os.path.join(DATA_DIR, "posted_items.json")
LOG_PATH = os.path.join(DATA_DIR, "post_log.json")
LOG_MAX_ENTRIES = 500
COOLDOWN_DAYS = 14
TOP_N = 3
POST_TEXT_LIMIT = 500

# genreId=0 は楽天市場の総合ランキング。特定ジャンルに絞りたい場合は
# ジャンル検索API (https://webservice.rakuten.co.jp/api/ichibagenresearch/) で
# 調べたジャンルIDをここに追加する。
GENRE_IDS = [0]

RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"

INTRO_PHRASES = [
    "楽天ランキング速報🔥",
    "今売れてるのはコレ！📈",
    "楽天民が選んだ人気商品✨",
    "見逃し注意の売れ筋ランキング👀",
    "今日の楽天TOP3はこちら🛒",
]

# 景品表示法(ステルスマーケティング規制)対応。アフィリエイトリンクを含む投稿には
# 必ずPRであることを明示する。本文冒頭の【PR】とハッシュタグの#PRの両方を付与する。
PR_PREFIX = "【PR】"
HASHTAGS = "#PR #楽天 #楽天ランキング #お得情報"


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def prune_state(state):
    cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
    pruned = {}
    for code, ts in state.items():
        try:
            if datetime.fromisoformat(ts) > cutoff:
                pruned[code] = ts
        except ValueError:
            continue
    return pruned


def fetch_ranking(genre_id):
    rakuten_affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    params = {
        "format": "json",
        "genreId": genre_id,
        "period": "realtime",
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
    }
    if rakuten_affiliate_id:
        params["affiliateId"] = rakuten_affiliate_id
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }
    resp = requests.get(RANKING_ENDPOINT, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    items = [entry["Item"] for entry in resp.json().get("Items", [])]
    for item in items:
        item["itemPrice"] = int(item["itemPrice"])
    # 楽天APIはrank(1位が最良)が降順(30位→1位)で返ってくるため、昇順に並べ替える
    items.sort(key=lambda item: item.get("rank", 0))
    return items


def pick_items(state):
    genre_order = GENRE_IDS[:]
    random.shuffle(genre_order)

    for genre_id in genre_order:
        items = fetch_ranking(genre_id)
        fresh = [item for item in items if item["itemCode"] not in state]
        if len(fresh) >= TOP_N:
            return fresh[:TOP_N]

    # 全ジャンルでクールダウン中の商品しかない場合は、最初のジャンルの上位を使う
    items = fetch_ranking(genre_order[0])
    return items[:TOP_N]


def format_item_line(medal, item):
    headline = (item.get("catchcopy") or "").strip() or item["itemName"]
    if len(headline) > 38:
        headline = headline[:38] + "…"

    price = f"{item['itemPrice']:,}円"

    review_count = item.get("reviewCount") or 0
    try:
        review_average = float(item.get("reviewAverage") or 0)
    except ValueError:
        review_average = 0
    review_line = ""
    if review_count and review_average > 0:
        review_line = f"⭐{review_average}({review_count:,}件)\n"

    sale_badge = "⏰タイムセール中\n" if (item.get("startTime") or item.get("endTime")) else ""

    url = item.get("affiliateUrl") or item["itemUrl"]

    return f"{medal} {headline}\n{sale_badge}💰{price}\n{review_line}🔗{url}\n"


def build_post_text(items):
    intro = random.choice(INTRO_PHRASES)
    medals = ["🥇", "🥈", "🥉"]
    lines = [PR_PREFIX + intro, ""]

    for medal, item in zip(medals, items):
        lines.append(format_item_line(medal, item))

    lines.append(HASHTAGS)
    text = "\n".join(lines)
    return text[:POST_TEXT_LIMIT]


def append_log(items, permalink):
    log = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)

    log.append({
        "postedAt": datetime.now(timezone.utc).isoformat(),
        "permalink": permalink,
        "items": [
            {
                "name": item["itemName"],
                "price": item["itemPrice"],
                "url": item.get("affiliateUrl") or item["itemUrl"],
            }
            for item in items
        ],
    })
    log = log[-LOG_MAX_ENTRIES:]

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
