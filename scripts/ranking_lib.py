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

# 投稿対象のジャンル {ジャンルID: 投稿文に使うジャンル名}。実行のたびにランダムに1つ選ぶ。
# 楽天ROOMで売れやすい系統(生活雑貨・キッズベビー)に絞っている(調査日: 2026-10-06)。
# 総合ランキングにしたい場合は {0: "楽天"} にする。IDは楽天のジャンル検索API
# (https://webservice.rakuten.co.jp/api/ichibagenresearch/) で確認できる。
GENRES = {
    100804: "インテリア・収納",
    558944: "キッチン用品",
    215783: "日用品雑貨",
    100533: "キッズ・ベビー",
}
GENRE_IDS = list(GENRES)

# 報酬率がこの値(%)未満の商品は除外する(例: 楽天ブックスは2%)。0にすると無効
MIN_AFFILIATE_RATE = 4.0
# 除外するショップコード(書籍・CD予約など。楽天ブックス = "book")
EXCLUDE_SHOP_CODES = {"book"}

RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"

# {genre} はジャンル名に置き換わる
INTRO_PHRASES = [
    "楽天{genre}ランキング速報🔥",
    "{genre}で今売れてるのはコレ！📈",
    "{genre}の人気商品はこちら✨",
    "見逃し注意の{genre}売れ筋👀",
    "今日の楽天{genre}TOP3🛒",
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
        item["genreName"] = GENRES.get(genre_id, "")
    items = [item for item in items if is_eligible(item)]
    # 楽天APIはrank(1位が最良)が降順(30位→1位)で返ってくるため、昇順に並べ替える
    items.sort(key=lambda item: item.get("rank", 0))
    return items


def is_eligible(item):
    """報酬率が低い商品・除外ショップの商品を取り除く"""
    if item.get("shopCode") in EXCLUDE_SHOP_CODES:
        return False
    try:
        rate = float(item.get("affiliateRate") or 0)
    except ValueError:
        rate = 0
    return rate >= MIN_AFFILIATE_RATE


def shorten_url(url):
    """is.gd(無料・APIキー不要)でURLを短縮する。失敗時は元のURLをそのまま返す。"""
    try:
        resp = requests.get(
            "https://is.gd/create.php",
            params={"format": "simple", "url": url},
            timeout=5,
        )
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
    except requests.RequestException:
        pass
    return url


def pick_items(state):
    genre_order = GENRE_IDS[:]
    random.shuffle(genre_order)

    for genre_id in genre_order:
        items = fetch_ranking(genre_id)
        fresh = [item for item in items if item["itemCode"] not in state]
        if len(fresh) >= TOP_N:
            picked = fresh[:TOP_N]
            break
    else:
        # 全ジャンルでクールダウン中の商品しかない場合は、最初のジャンルの上位を使う
        picked = fetch_ranking(genre_order[0])[:TOP_N]

    for item in picked:
        item["displayUrl"] = shorten_url(item.get("affiliateUrl") or item["itemUrl"])
    return picked


def format_item_line(medal, item, include_hook=True, include_review=True):
    name = item["itemName"]
    if len(name) > 26:
        name = name[:26] + "…"

    # catchcopyは商品固有のフックのこともあれば、ショップ全体の定型文
    # (例:「楽天ブックスならいつでも送料無料」)のこともある。
    # 商品名と重複していない場合だけ、補足として添える。
    hook_line = ""
    if include_hook:
        catchcopy = (item.get("catchcopy") or "").strip()
        if catchcopy and catchcopy not in name:
            short_catchcopy = catchcopy if len(catchcopy) <= 28 else catchcopy[:28] + "…"
            hook_line = f"📣{short_catchcopy}\n"

    price = f"{item['itemPrice']:,}円"

    review_line = ""
    if include_review:
        review_count = item.get("reviewCount") or 0
        try:
            review_average = float(item.get("reviewAverage") or 0)
        except ValueError:
            review_average = 0
        if review_count and review_average > 0:
            review_line = f"⭐{review_average}({review_count:,}件)\n"

    sale_badge = "⏰タイムセール中\n" if (item.get("startTime") or item.get("endTime")) else ""

    url = item.get("displayUrl") or item.get("affiliateUrl") or item["itemUrl"]

    return f"{medal} {name}\n{hook_line}{sale_badge}💰{price}\n{review_line}🔗{url}\n"


def build_post_text(items):
    genre = (items[0].get("genreName") or "") if items else ""
    intro = random.choice(INTRO_PHRASES).format(genre=genre)
    medals = ["🥇", "🥈", "🥉"]

    # アフィリエイトURLが長いと500字を超えることがある。
    # URLの途中で切れて壊れたリンクにならないよう、情報量→商品数の順に段階的に削る。
    # 1) catchcopyを削る 2) レビュー情報も削る 3) それでも収まらなければ商品数を減らす
    for n in range(len(items), 0, -1):
        for include_hook, include_review in [(True, True), (False, True), (False, False)]:
            item_lines = [
                format_item_line(medal, item, include_hook, include_review)
                for medal, item in zip(medals[:n], items[:n])
            ]
            text = "\n".join([PR_PREFIX + intro, ""] + item_lines + [HASHTAGS])
            if len(text) <= POST_TEXT_LIMIT:
                return text

    return "\n".join([PR_PREFIX + intro, "", HASHTAGS])[:POST_TEXT_LIMIT]


# 楽天ROOM用(手動投稿)。事実に基づく表現のみ使い、「使ってみた」等の体験談は書かない。
# アフィリエイト投稿のため#PRを付与する。文面は自由に編集してよい。
ROOM_HASHTAGS = "#PR #楽天ROOM"
ROOM_COMMENT_TEMPLATES = [
    "楽天{genre}ランキング{rank}位の人気アイテム。{price}円{review}",
    "{genre}で今売れている{rank}位！{price}円{review}",
    "{genre}ランキング{rank}位に入っていた注目商品。{price}円{review}",
]


def build_room_comment(item):
    review_count = item.get("reviewCount") or 0
    try:
        review_average = float(item.get("reviewAverage") or 0)
    except ValueError:
        review_average = 0
    review = f"、レビュー⭐{review_average}({review_count:,}件)" if review_count and review_average > 0 else ""

    comment = random.choice(ROOM_COMMENT_TEMPLATES).format(
        genre=item.get("genreName") or "",
        rank=item.get("rank", "?"),
        price=f"{item['itemPrice']:,}",
        review=review,
    )
    return f"{comment}\n{ROOM_HASHTAGS}"


def build_room_section(items):
    medals = ["🥇", "🥈", "🥉"]
    blocks = []
    for medal, item in zip(medals, items):
        name = item["itemName"]
        if len(name) > 40:
            name = name[:40] + "…"
        blocks.append(
            f"### {medal} {name}\n"
            f"商品ページ(ROOMでコレクトする): {item['itemUrl']}\n\n"
            f"```\n{build_room_comment(item)}\n```"
        )
    return "\n\n".join(blocks)


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
