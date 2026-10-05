"""各ジャンルのランキング取得状況を確認する診断用スクリプト(件数のみ表示。キーは表示しない)。

使い方(PowerShell): py scripts\\check_genres.py
「取得」= 楽天APIが返した件数 / 「対象」= 報酬率・除外ショップの条件を満たした件数
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import ranking_lib as r


def main():
    print(f"条件: 報酬率{r.MIN_AFFILIATE_RATE}%以上 / 除外ショップ: {sorted(r.EXCLUDE_SHOP_CODES)}")
    for genre_id, name in r.GENRES.items():
        try:
            items = r.fetch_ranking(genre_id, apply_filter=False)
        except RuntimeError as e:
            print(f"{name}({genre_id}): 取得失敗 {e}")
            continue
        eligible = [item for item in items if r.is_eligible(item)]
        rates = Counter(str(item.get("affiliateRate")) for item in items)
        print(f"{name}({genre_id}): 取得{len(items)}件 / 対象{len(eligible)}件 / 報酬率の内訳 {dict(rates)}")


if __name__ == "__main__":
    main()
