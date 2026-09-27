# PC上でタスクスケジューラから定期実行するスクリプト。
# 楽天APIがGitHub Actionsのサーバーからのアクセスをブロックするため、
# 「投稿案を作る」処理だけをローカルPCから実行する。
#
# 事前に、以下のユーザー環境変数を設定しておくこと(setxコマンド、またはシステムのプロパティから):
#   RAKUTEN_APP_ID
#   RAKUTEN_ACCESS_KEY
#   RAKUTEN_AFFILIATE_ID
#   GITHUB_TOKEN        (Issues・Contentsの書き込み権限を持つPAT)
#   GITHUB_REPOSITORY   (例: takumi3334/rakuten-sns-bot)

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $PSScriptRoot
Set-Location $RepoDir

git pull --quiet

python scripts\prepare_post.py

git add data\schedule.json
$staged = git diff --staged --name-only
if ($staged) {
    git commit -m "Mark schedule slot as prepared (local run)" --quiet
    git push --quiet
}
