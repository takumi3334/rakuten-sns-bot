"""投稿ごとの閲覧数・いいね数などをThreads APIから取得し、data/post_log.json に書き込む。

GitHub Actions(update-insights.yml)で毎日実行する。
必要な権限: threads_basic, threads_manage_insights(アクセストークンに含まれている必要がある)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
THREADS_API_BASE = "https://graph.threads.net/v1.0"

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "post_log.json")
METRICS = ["views", "likes", "replies", "reposts", "quotes"]
# 投稿から何日間、数値を更新し続けるか(古い投稿は数値がほぼ動かないため)
UPDATE_DAYS = 30


class InsightsError(Exception):
    pass


def fetch_insights(media_id):
    resp = requests.get(
        f"{THREADS_API_BASE}/{media_id}/insights",
        params={"metric": ",".join(METRICS), "access_token": THREADS_ACCESS_TOKEN},
        timeout=15,
    )
    if resp.status_code != 200:
        # トークンを含む可能性があるため、URLや全文は出さず、エラーメッセージだけを出す
        try:
            message = resp.json().get("error", {}).get("message", "")
        except ValueError:
            message = ""
        raise InsightsError(f"HTTP {resp.status_code} {message}".strip())

    result = {}
    for metric in resp.json().get("data", []):
        values = metric.get("values") or []
        if values:
            result[metric["name"]] = values[0].get("value", 0)
    return result


def main():
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        log = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=UPDATE_DAYS)
    updated = 0
    skipped_no_id = 0

    for entry in log:
        media_id = entry.get("mediaId")
        if not media_id:
            skipped_no_id += 1
            continue
        if datetime.fromisoformat(entry["postedAt"]) < cutoff:
            continue
        try:
            entry["insights"] = fetch_insights(media_id)
        except InsightsError as e:
            print(f"インサイト取得に失敗: {e}")
            print("アクセストークンに threads_manage_insights 権限があるか確認してください。")
            sys.exit(1)
        entry["insightsUpdatedAt"] = datetime.now(timezone.utc).isoformat()
        updated += 1

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"更新: {updated}件 / 投稿IDなし(取得対象外): {skipped_no_id}件")


if __name__ == "__main__":
    main()
