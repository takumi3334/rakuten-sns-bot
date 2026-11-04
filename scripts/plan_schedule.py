import json
import os
import random
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")

JST = ZoneInfo("Asia/Tokyo")

# 投稿案を作る時間帯(JST)。1つの時間帯につき1枠で、その範囲内でランダムな時刻が選ばれる。
# 枠の数 = 1日の投稿上限。増減させたい場合は、時間帯を足す・消す。
# 1枠目を朝(9〜11時)に固定しているのは、投稿履歴の分析(2026-11-04)で朝の閲覧数が高めだったための実験。
# ※ 実際にThreadsに公開されるのは、投稿案を承認(approve)した時刻。朝に承認すると朝の投稿になる。
SLOT_WINDOWS = [
    (dtime(9, 0), dtime(11, 0)),
    (dtime(11, 0), dtime(16, 30)),
    (dtime(16, 30), dtime(22, 0)),
]


def generate_times(today):
    times = []
    for start, end in SLOT_WINDOWS:
        start_dt = datetime.combine(today, start, tzinfo=JST)
        end_dt = datetime.combine(today, end, tzinfo=JST)
        window_minutes = int((end_dt - start_dt).total_seconds() // 60)
        chosen = start_dt + timedelta(minutes=random.randint(0, window_minutes - 1))
        times.append(chosen.strftime("%H:%M"))
    return times


def main():
    today = datetime.now(JST).date()
    schedule = {
        "date": today.isoformat(),
        "times": generate_times(today),
        "done": [],
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    print("本日の投稿予定時刻:", schedule["times"])


if __name__ == "__main__":
    main()
