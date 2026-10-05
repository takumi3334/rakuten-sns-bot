# 楽天ランキング自動投稿bot(副業のアフィリエイト自動化)

楽天市場の売れ筋ランキングを取得し、アフィリエイトリンク付きで **Threads** に自動投稿する Python 製bot。
(置き場所: `rakuten-sns-bot` フォルダ直下に `CLAUDE.md`)

## 仕組み(READMEより)
* **必ず人間の承認を経てから公開**する。投稿案は GitHub Issue として起票 → `approve` とコメントで投稿
* 毎日 0:05(JST)に GitHub Actions がその日の投稿時刻を3回分ランダムに決定(1日の上限は既定3件)
* 投稿案の作成(楽天APIを呼ぶ処理)は**たくみさんのPCで定期実行**する(`scripts/run_local_prepare.ps1`)
  * 理由: 楽天APIが GitHub Actions(海外データセンター)からのアクセスを `CLIENT_IP_NOT_ALLOWED` でブロックするため
* 承認後の投稿・トークン更新(週1)は GitHub Actions で自動
* 投稿済み商品は14日間再投稿しない(`data/posted_items.json`)。履歴は `data/post_log.json`
* 主なスクリプト: `scripts/` の `plan_schedule.py` / `prepare_post.py` / `publish_approved.py` / `ranking_lib.py` / `refresh_token.py`

## 守るべき方針(変えてはいけない前提)
* **投稿先は Threads のみ。** X(Twitter)は APIが従量課金(URL付き投稿1回$0.20)になり無料運用できないため切り替えた
* **楽天ROOMは自動投稿の対象外**(公式APIがなく規約リスク)
* **`【PR】` 表記と `#PR` ハッシュタグの自動付与は必須**(景品表示法対応)。外さない
* 1日あたりの上限 + ランダムな時間差を維持する
* 1回の投稿の3商品は、毎回すべて別ジャンルにする(同じジャンルを重ねない)
* 公開前の人間レビュー(Issue承認)を省略しない
* Instagram / TikTok は将来の拡張候補(現時点では対象外)

## 取り扱い注意
* `.env`、Threadsのトークン、楽天の App ID / Access Key、`GH_PAT` は**読まない・表示しない・ログに出さない**

## 注意点(育てていく欄)
* (追記は承認制)
