import os
import json
import random
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

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
    568199: "日用消耗品",
}
GENRE_IDS = list(GENRES)

# 報酬率がこの値(%)未満の商品は除外する。0にすると無効
# 実測(2026-10-06): キッズ・ベビーは4%、他の4ジャンルは3%。楽天ブックス・ゲーム・PCなどは2%
MIN_AFFILIATE_RATE = 3.0
# 除外するショップコード(書籍・CD予約など。楽天ブックス = "book")
EXCLUDE_SHOP_CODES = {"book"}

RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"

# 楽天APIは連続アクセスに制限がある(目安: 1秒に1回)。呼び出しの最小間隔(秒)
RAKUTEN_MIN_INTERVAL = 1.2
RAKUTEN_MAX_RETRIES = 4
_last_api_call = 0.0

# 1回の投稿には3つの別ジャンルの商品を載せるため、導入文はジャンルを特定しない表現にする
INTRO_PHRASES = [
    "楽天ジャンル別ランキング速報🔥",
    "ジャンル別で今売れてるのはコレ！📈",
    "楽天民が選んだ人気商品✨",
    "見逃し注意の売れ筋ランキング👀",
    "今日の楽天ジャンル別TOP🛒",
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


def fetch_ranking(genre_id, apply_filter=True):
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
    global _last_api_call
    resp = None
    for attempt in range(RAKUTEN_MAX_RETRIES):
        wait = RAKUTEN_MIN_INTERVAL - (time.monotonic() - _last_api_call)
        if wait > 0:
            time.sleep(wait)
        resp = requests.get(RANKING_ENDPOINT, params=params, headers=headers, timeout=15)
        _last_api_call = time.monotonic()
        if resp.status_code != 429:
            break
        time.sleep(2 * (attempt + 1))  # 制限に当たったら少し待って再試行

    if resp.status_code >= 400:
        # URLにApp ID・Access Keyが含まれるため、例外メッセージにURLを出さない
        raise RuntimeError(f"楽天ランキングAPIエラー: HTTP {resp.status_code} (genreId={genre_id})")
    items = [entry["Item"] for entry in resp.json().get("Items", [])]
    for item in items:
        item["itemPrice"] = int(item["itemPrice"])
        item["genreId"] = genre_id
        item["genreName"] = GENRES.get(genre_id, "")
    if apply_filter:
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
    """TinyURL(無料・APIキー不要)でURLを短縮する。失敗時は元のURLをそのまま返す。
    (is.gdは楽天のアフィリエイトURLを受け付けなかったため、TinyURLを使う)"""
    try:
        resp = requests.get(
            "https://tinyurl.com/api-create.php",
            params={"url": url},
            timeout=8,
        )
        if resp.status_code == 200 and resp.text.startswith("https://tinyurl.com/"):
            return resp.text.strip()
    except requests.RequestException:
        pass
    return url


def pick_items(state):
    """TOP_N件を、すべて別ジャンルから選ぶ(各ジャンルで最上位の未投稿商品を1件ずつ)。"""
    genre_order = GENRE_IDS[:]
    random.shuffle(genre_order)

    rankings = {}
    picked = []
    for genre_id in genre_order:
        rankings[genre_id] = fetch_ranking(genre_id)
        fresh = [item for item in rankings[genre_id] if item["itemCode"] not in state]
        if fresh:
            picked.append(fresh[0])
        if len(picked) == TOP_N:
            break

    if len(picked) < TOP_N:
        # 未投稿の商品が足りないジャンルは、クールダウン中の商品で補う(同じジャンルは重ねない)
        used_genres = {item["genreId"] for item in picked}
        for genre_id in genre_order:
            if len(picked) == TOP_N:
                break
            if genre_id not in used_genres and rankings.get(genre_id):
                picked.append(rankings[genre_id][0])

    # 各商品のジャンル内順位が高い順に並べる
    picked.sort(key=lambda item: item.get("rank", 0))

    for item in picked:
        item["displayUrl"] = shorten_url(item.get("affiliateUrl") or item["itemUrl"])
    return picked


def rank_label(item):
    """「ジャンル名+そのジャンルでの順位」。ジャンルごとに順位が違うため、誤認を避けて明記する。"""
    return f"{item.get('genreName') or ''}{item.get('rank', '')}位"


def format_item_line(item, include_hook=True, include_review=True):
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

    return f"🏆{rank_label(item)} {name}\n{hook_line}{sale_badge}💰{price}\n{review_line}🔗{url}\n"


def build_post_text(items):
    intro = random.choice(INTRO_PHRASES)

    # アフィリエイトURLが長いと500字を超えることがある。
    # URLの途中で切れて壊れたリンクにならないよう、情報量→商品数の順に段階的に削る。
    # 1) catchcopyを削る 2) レビュー情報も削る 3) それでも収まらなければ商品数を減らす
    for n in range(len(items), 0, -1):
        for include_hook, include_review in [(True, True), (False, True), (False, False)]:
            item_lines = [
                format_item_line(item, include_hook, include_review)
                for item in items[:n]
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


def plain_item_url(item):
    """アフィリエイト用の長いURLから、通常の商品ページURL(pc=の中身)を取り出す。無ければそのまま返す。"""
    url = item["itemUrl"]
    pc = parse_qs(urlparse(url).query).get("pc")
    return pc[0] if pc else url


def build_room_section(items):
    blocks = []
    for item in items:
        name = item["itemName"]
        if len(name) > 40:
            name = name[:40] + "…"
        blocks.append(
            f"### 🏆{rank_label(item)} {name}\n"
            f"商品ページ(ROOMでコレクトする): {plain_item_url(item)}\n\n"
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
