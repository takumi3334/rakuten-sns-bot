import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from ranking_lib import load_state, save_state, append_log

THREADS_USER_ID = os.environ["THREADS_USER_ID"]
THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
THREADS_API_BASE = "https://graph.threads.net/v1.0"
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]


def get_issue_body():
    result = subprocess.run(
        ["gh", "issue", "view", ISSUE_NUMBER, "--json", "body"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["body"]


def extract_payload(body):
    match = re.search(r"<!-- POST_DATA: (.*?) -->", body, re.DOTALL)
    if not match:
        raise RuntimeError("Issue本文からPOST_DATAが見つかりませんでした")
    return json.loads(match.group(1))


def post_to_threads(text):
    create_resp = requests.post(
        f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": THREADS_ACCESS_TOKEN},
        timeout=15,
    )
    if create_resp.status_code >= 300:
        raise RuntimeError(f"Threads container creation failed: {create_resp.status_code} {create_resp.text}")
    creation_id = create_resp.json()["id"]

    # コンテナ作成直後は反映に時間がかかることがあるため少し待つ
    time.sleep(5)

    publish_resp = requests.post(
        f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish",
        data={"creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN},
        timeout=15,
    )
    if publish_resp.status_code >= 300:
        raise RuntimeError(f"Threads publish failed: {publish_resp.status_code} {publish_resp.text}")
    return publish_resp.json()


def fetch_permalink(media_id):
    resp = requests.get(
        f"{THREADS_API_BASE}/{media_id}",
        params={"fields": "permalink", "access_token": THREADS_ACCESS_TOKEN},
        timeout=15,
    )
    if resp.status_code >= 300:
        return None
    return resp.json().get("permalink")


def finish_issue(comment):
    subprocess.run(["gh", "issue", "comment", ISSUE_NUMBER, "--body", comment], check=True)
    subprocess.run(["gh", "issue", "close", ISSUE_NUMBER], check=True)


def main():
    body = get_issue_body()
    payload = extract_payload(body)
    items = payload["items"]

    result = post_to_threads(payload["text"])
    permalink = fetch_permalink(result["id"])

    state = load_state()
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in items:
        state[item["itemCode"]] = now_iso
    save_state(state)

    log_items = [
        {
            "itemName": item["itemName"],
            "itemPrice": item["itemPrice"],
            "affiliateUrl": item["url"],
            "itemUrl": item["url"],
        }
        for item in items
    ]
    append_log(log_items, permalink)

    comment = "投稿しました。" + (f"\n{permalink}" if permalink else "")
    finish_issue(comment)
    print("公開完了:", permalink)


if __name__ == "__main__":
    main()
