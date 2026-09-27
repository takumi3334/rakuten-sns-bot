import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from ranking_lib import load_state, prune_state, pick_items, build_post_text

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
JST = ZoneInfo("Asia/Tokyo")


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


def ensure_labels():
    """pending-review・approvedラベルが無ければ作成する(GitHub Web UIでの手動作成を不要にする)"""
    labels = [
        ("pending-review", "FFA500", "レビュー待ちの投稿案"),
        ("approved", "22C55E", "承認済み。このラベルを付けると自動で公開される"),
    ]
    for name, color, description in labels:
        subprocess.run(
            ["gh", "label", "create", name, "--color", color, "--description", description, "--force"],
            check=False,
        )


def create_review_issue(text, items):
    ensure_labels()

    payload = {
        "text": text,
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
        "承認する場合は、このIssueに `approved` ラベルを付けてください(自動で公開されます)。\n"
        "却下する場合は、このIssueをCloseしてください。\n\n"
        f"<!-- POST_DATA: {json.dumps(payload, ensure_ascii=False)} -->"
    )

    title = f"投稿レビュー: {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(body)
        body_path = f.name

    subprocess.run(
        [
            "gh", "issue", "create",
            "--title", title,
            "--body-file", body_path,
            "--label", "pending-review",
        ],
        check=True,
    )


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
