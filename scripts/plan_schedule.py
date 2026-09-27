import json
import os
import random
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")

JST = ZoneInfo("Asia/Tokyo")

# 1日あたりの投稿上限。増減させたい場合はここを変更する。
DAILY_POST_CAP = 3

# 投稿を行う時間帯(この範囲内でランダムな時刻が選ばれる)
WINDOW_START = dtime(9, 0)
WINDOW_END = dtime(22, 0)


def generate_times(today):
    start_dt = datetime.combine(today, WINDOW_START, tzinfo=JST)
    end_dt = datetime.combine(today, WINDOW_END, tzinfo=JST)
    total_minutes = int((end_dt - start_dt).total_seconds() // 60)
    slot_minutes = total_minutes // DAILY_POST_CAP

    times = []
    for i in range(DAILY_POST_CAP):
        slot_start = start_dt + timedelta(minutes=slot_minutes * i)
        offset = random.randint(0, slot_minutes - 1)
        chosen = slot_start + timedelta(minutes=offset)
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
