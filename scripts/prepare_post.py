import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(__file__))
from ranking_lib import load_state, prune_state, pick_items, build_post_text

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
JST = ZoneInfo("Asia/Tokyo")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # 例: "takumi3334/rakuten-sns-bot"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def load_schedule():
    if not os.path.exists(SCHEDULE_PATH):
        return None
    with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_schedule(schedule):
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)


def due_slot(schedule):
    """本日分のスケジュールの中で、現在時刻を過ぎていてまだ未消化の枠を1つ返す"""
    now = datetime.now(JST)
    today = now.date().isoformat()
    if schedule is None or schedule.get("date") != today:
        return None

    current_hm = now.strftime("%H:%M")
    for slot in schedule["times"]:
        if slot in schedule.get("done", []):
            continue
        if slot <= current_hm:
            return slot
    return None


def top_image_url(item):
    urls = item.get("mediumImageUrls") or []
    if urls and urls[0].get("imageUrl"):
        return urls[0]["imageUrl"]
    return None


def create_review_issue(text, items):
    payload = {
        "text": text,
        "imageUrl": top_image_url(items[0]) if items else None,
        "items": [
            {
                "itemCode": item["itemCode"],
                "itemName": item["itemName"],
                "itemPrice": item["itemPrice"],
                "url": item.get("affiliateUrl") or item["itemUrl"],
            }
            for item in items
        ],
    }
    body = (
        "## 投稿案\n\n"
        "```\n" + text + "\n```\n\n"
        "承認する場合は、このIssueに **`approve`** とコメントしてください(自動で公開されます)。\n"
        "却下する場合は、このIssueをCloseしてください。\n\n"
        f"<!-- POST_DATA: {json.dumps(payload, ensure_ascii=False)} -->"
    )

    title = f"投稿レビュー: {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}"

    resp = requests.post(
        f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/issues",
        headers=GITHUB_HEADERS,
        json={"title": title, "body": body},
        timeout=15,
    )
    resp.raise_for_status()


def main():
    schedule = load_schedule()
    slot = due_slot(schedule)
    if slot is None:
        print("本日はまだ次の投稿予定時刻になっていません")
        return

    state = prune_state(load_state())
    items = pick_items(state)
    if not items:
        print("投稿できる商品が見つかりませんでした")
        return

    text = build_post_text(items)
    create_review_issue(text, items)

    schedule.setdefault("done", []).append(slot)
    save_schedule(schedule)
    print(f"{slot} の投稿案をレビューIssueとして作成しました")


if __name__ == "__main__":
    main()
