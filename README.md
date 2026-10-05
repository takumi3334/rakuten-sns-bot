# 楽天ランキング自動投稿bot

楽天市場の売れ筋ランキングを取得し、アフィリエイトリンク付きでThreadsに自動投稿するbotです。
GitHub Actionsの無料枠でスケジュール実行するため、追加費用はかかりません。

※ 当初はX(Twitter)を想定していましたが、Xの開発者APIが完全従量課金制に変わり
(URLを含む投稿は1回$0.20)、無料運用ができなくなったため、無料のThreads APIに切り替えています。

## 仕組み

完全自動では投稿せず、**必ず人間の承認を経てから公開する**構成になっている。

※ 楽天のランキングAPIは、**GitHub Actionsのサーバー(海外データセンター)からのアクセスを
`CLIENT_IP_NOT_ALLOWED`エラーでブロックする**ことが判明した(Cloudflare Workers経由でも同様にブロックされた)。
そのため「投稿案を作る」部分(楽天APIを呼ぶ部分)だけは、**ご自身のPCから定期的に実行**する構成になっている。
それ以外(スケジュール決定・承認後の投稿・トークン更新)は今まで通りクラウドで完全自動。

1. 毎日0:05(JST)、`plan-schedule.yml`(クラウド/GitHub Actions)がその日の投稿時刻を3回分、9:00〜22:00の範囲でランダムに決める(`data/schedule.json`)。1日の投稿上限もここで決まる(デフォルト3件/日)
2. **ご自身のPCで**タスクスケジューラにより定期的に(例: 1時間おき)`scripts/run_local_prepare.ps1` が実行され、「予定時刻を過ぎていて未消化の枠」がないか確認する
3. 該当する枠があれば、楽天商品ランキングAPI(無料・公式)から上位商品を取得し、ランキング形式の投稿文(**景品表示法対応の`【PR】`表記・`#PR`ハッシュタグ付き**)を組み立てて、**GitHub Issueとしてレビュー起票**する(まだ投稿はしない)
4. 起票されたIssueを見て、内容が問題なければ **`approve` とコメント**する。問題があればIssueをCloseする(却下)。この操作はスマホのGitHubアプリからでも可能
5. `approve` とコメントされた瞬間、`publish-approved.yml`(クラウド/GitHub Actions)が自動で起動し、Threads API (Graph API, OAuth2) で実際に投稿する。**この部分はPCの状態に関係なく動く**
6. 投稿済み商品は `data/posted_items.json` に記録し、14日間は再投稿しない
7. 投稿履歴は `data/post_log.json` にも記録され、`index.html`(GitHub Pagesダッシュボード)から確認できる
8. Threadsのアクセストークン(60日間有効)は、別のワークフローで毎週自動更新される

## セットアップ手順

### 1. Threadsアカウントの準備

このbot専用の**新しいThreadsアカウント**を作成する(既存の本業・ブランドアカウントとは分ける)。
Threads APIはInstagramアカウントに紐づくThreadsアカウントを使うため、新しいInstagramアカウント
(またはThreadsのみで使う用のアカウント)を用意し、スマホのThreadsアプリでThreadsアカウントを作成する。

### 2. Meta Appの作成

1. https://developers.facebook.com/apps/ にアクセスしてログイン
2. 「アプリを作成」→ ユースケースで **「Threads」** を選択
3. 作成後、アプリのダッシュボードで **Threads APIの設定** に進み、以下を控える
   - **Threads App ID**
   - **Threads App Secret**
   - (通常のMeta App IDとは別に、Threads専用のIDとSecretが発行される点に注意)
4. ダッシュボードの「Threads use case」設定画面で、**リダイレクトURI**を1つ登録する
   (実際に何かを受け取るサーバーは不要。例: `https://example.com/callback` のようなダミーURLでよい)
5. 「App roles」→「Roles」で **自分自身をThreadsテスターとして追加**し、
   Threadsアプリ側(アカウント設定 > テスター招待)で招待を承認する
   - 自分のアカウントにだけ投稿するなら、これで**Metaのアプリレビューは不要**

### 3. 初回アクセストークンの取得(手動・1回だけ)

1. 以下のURLの `<THREADS_APP_ID>` と `<REDIRECT_URI>` を自分の値に置き換えてブラウザで開く

```
https://threads.net/oauth/authorize?client_id=<THREADS_APP_ID>&redirect_uri=<REDIRECT_URI>&scope=threads_basic,threads_content_publish&response_type=code
```

2. Threadsアカウントでログインし、許可する
3. リダイレクト先のURLに `?code=xxxxx` が付与されるので、その `code` の値をコピーする
   (末尾に `#_` が付いていたら、それは含めない)
4. ローカルで以下を実行してトークンを交換する

```bash
pip install -r requirements.txt
export THREADS_APP_ID=xxxx        # PowerShellなら $env:THREADS_APP_ID="xxxx"
export THREADS_APP_SECRET=xxxx
export THREADS_REDIRECT_URI=https://example.com/callback
python scripts/get_initial_token.py "<控えた認可コード>"
```

5. 表示される `THREADS_USER_ID` と `THREADS_ACCESS_TOKEN` を控える(これがGitHub Secretsに登録する値)

### 4. 楽天APIの準備

1. https://webservice.rakuten.co.jp/ の「Your Apps」からアプリを確認(未作成なら「New App」で作成)
2. 各アプリには **App ID** と **Access Key** が別々に発行されている(2026年の仕様変更で追加された認証情報)。両方を控える
   - App IDはUUID形式(例: `85544306-e87e-40aa-acbb-6053c88f15a8`)
   - Access Keyも同じアプリ管理画面に表示されている
3. 既にお持ちの楽天アフィリエイトIDを控える(アフィリエイトIDは開発者につき1つ。全アプリで共通)

### 5. GitHub Personal Access Tokenの作成

トークン自動更新ワークフロー、および**ローカルPCから投稿案を作る処理**の両方で使う、共通のトークンを作成する。

1. https://github.com/settings/personal-access-tokens/new にアクセス
2. Repository access で該当リポジトリ(`rakuten-sns-bot`)のみを選択
3. Permissions で以下をすべて **Read and write** に設定
   - **Secrets**(トークン自動更新ワークフロー用)
   - **Issues**(投稿案のIssue作成用)
   - **Contents**(スケジュールファイルのpush用)
4. 発行されたトークンを控える(これを `GH_PAT` と、ローカルPCの `GITHUB_TOKEN` の両方に使う)

### 6. GitHubリポジトリの作成(未作成の場合)

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create rakuten-sns-bot --public --source=. --push
```

※ ダッシュボード(GitHub Pages)を使うため、リポジトリは **Public** にする。
投稿内容(商品名・価格・アフィリエイトURL)はThreads上でも公開情報なので問題ない。
GitHub Secretsに登録した値(APIキー等)は、リポジトリがPublicでも非公開のまま。

既にPrivateで作成済みの場合は、GitHubの該当リポジトリで
Settings → General → 一番下の「Danger Zone」→ **Change visibility → Make public** から変更する。

### 7. GitHub Pagesの有効化(ダッシュボード)

1. リポジトリの Settings → 左メニューの **Pages**
2. 「Build and deployment」の Source を **Deploy from a branch** に設定
3. Branch を `main` / `/ (root)` にして **Save**
4. 数分待つと `https://<あなたのユーザー名>.github.io/rakuten-sns-bot/` でダッシュボードが公開される
5. 以後、投稿が公開されるたびに `data/post_log.json` が自動更新され、ダッシュボードにも反映される

### 8. GitHub Secretsの登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret で以下を登録:

| Secret名 | 値 |
|---|---|
| `RAKUTEN_APP_ID` | 楽天アプリID(App ID) |
| `RAKUTEN_ACCESS_KEY` | 楽天Access Key |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトID |
| `THREADS_USER_ID` | 手順3で取得したThreadsユーザーID |
| `THREADS_ACCESS_TOKEN` | 手順3で取得した長期アクセストークン |
| `GH_PAT` | 手順5で発行したPersonal Access Token |

### 9. ローカルPCの設定(投稿案を作る処理)

**1回だけ**、PowerShellで以下を実行し、ユーザー環境変数を設定する(値は各自のものに置き換える)。
`setx` はターミナルを再起動しないと反映されないので、設定後は一度PowerShellを閉じて開き直すこと。

```powershell
setx RAKUTEN_APP_ID "85544306-e87e-40aa-acbb-6053c88f15a8"
setx RAKUTEN_ACCESS_KEY "楽天のAccess Key"
setx RAKUTEN_AFFILIATE_ID "559327ac.a79ca32c.559327ad.c0573395"
setx GITHUB_TOKEN "手順5で発行したPersonal Access Token"
setx GITHUB_REPOSITORY "takumi3334/rakuten-sns-bot"
```

続けて、タスクスケジューラに登録する。

1. Windowsの検索から「タスクスケジューラ」を開く
2. 右側の **「タスクの作成」**(「基本タスクの作成」ではなく)をクリック
3. **全般**タブ: 名前を `rakuten-prepare-post` などにする。「最上位の特権で実行する」にチェック
4. **トリガー**タブ → 新規 → 「タスクの開始」を **「1 回」** にし、開始時刻を適当な近い時刻に設定 → 詳細設定の **「繰り返し間隔」を1時間**、**「継続時間」を無期限** にチェック
5. **操作**タブ → 新規 →
   - プログラム/スクリプト: `powershell.exe`
   - 引数の追加: `-ExecutionPolicy Bypass -File "C:\Users\takum\Desktop\開発アプリ\開発アプリ\rakuten-sns-bot\scripts\run_local_prepare.ps1"`
6. **条件**タブ: 「AC電源接続時のみ」などお好みで調整(ノートPCの場合)
7. OKで保存

これで、PCが起動しているあいだ、1時間おきに投稿案の作成をチェックするようになる。

### 10. 動作確認

1. GitHubリポジトリの Actions タブ → **"Plan Daily Posting Schedule"** → "Run workflow" で手動実行し、`data/schedule.json` が作られるか確認する
2. PowerShellで手動実行して確認する

   ```powershell
   cd "C:\Users\takum\Desktop\開発アプリ\開発アプリ\rakuten-sns-bot"
   powershell -ExecutionPolicy Bypass -File scripts\run_local_prepare.ps1
   ```

   - 予定時刻をまだ過ぎていない場合は何も起きない(GitHub上で`data/schedule.json`の時刻を手で過去の時刻に書き換えてpushしてから再実行すると確認しやすい)
3. Issues タブに **「投稿レビュー: ...」** というIssueが作られているか確認する
4. 内容を確認し、問題なければそのIssueに **`approve` とコメント**する
5. 自動で **"Publish Approved Post"** ワークフローが起動し、Threadsに投稿される。Issueには自動でコメントが付き、Closeされる
6. ダッシュボード(`https://<あなたのユーザー名>.github.io/rakuten-sns-bot/`)を開いて投稿履歴が表示されるか確認する

以降は `plan-schedule.yml`(クラウド、毎日0:05 JST)と、ローカルPCのタスクスケジューラ(1時間おき)が
投稿案を作り、`approve` とコメントするだけで公開される運用になる。
また `.github/workflows/refresh-token.yml` が毎週月曜に自動でアクセストークンを更新する。

## カスタマイズ

- **1日の投稿上限・時間帯**: `scripts/plan_schedule.py` の `DAILY_POST_CAP`(デフォルト3件)、`WINDOW_START`/`WINDOW_END`(デフォルト9:00〜22:00)を変更
- **投稿案のチェック頻度**: タスクスケジューラのトリガー設定(繰り返し間隔)を変更
- **投稿ジャンルの変更**: `scripts/ranking_lib.py` の `GENRES`(`{ジャンルID: 投稿文に使う名前}`)を編集。IDは[楽天ジャンル検索API](https://webservice.rakuten.co.jp/api/ichibagenresearch/)で確認。実行のたびにランダムで1ジャンルが選ばれる
- **報酬率・ショップの除外**: `MIN_AFFILIATE_RATE`(既定4.0%未満は除外)、`EXCLUDE_SHOP_CODES`(既定は楽天ブックス)を変更
- **投稿文のトーン**: `scripts/ranking_lib.py` の `INTRO_PHRASES` のリストに好きな煽り文句を追加してバリエーションを増やす
- **クールダウン期間**: `scripts/ranking_lib.py` の `COOLDOWN_DAYS`(デフォルト14日)を変更
- **PR表記**: `scripts/ranking_lib.py` の `PR_PREFIX` / `HASHTAGS` を変更(削除は非推奨。景品表示法対応のため)

## ローカルでのテスト方法

`prepare_post.py` は `GITHUB_TOKEN`/`GITHUB_REPOSITORY` の環境変数があれば動く(`gh` CLIのインストールは不要)。
`publish_approved.py` は GitHub Actions上でのみ実行する想定(`gh` CLIとGITHUB_TOKENが自動で使える)。

```powershell
pip install -r requirements.txt
# setxで設定済みの環境変数(RAKUTEN_*, GITHUB_TOKEN, GITHUB_REPOSITORY)を使う

# その日の投稿スケジュールを生成(Threads/楽天の認証情報は不要)
python scripts\plan_schedule.py

# 予定時刻を過ぎていればレビューIssueを作成
python scripts\prepare_post.py
```

## 注意点

- GitHub Actionsのスケジュール実行は、リポジトリに60日間コミットが無いと自動停止する仕様がある。定期的に何かしらコミットするか、稼働状況を月1回程度確認すること
- Threadsの投稿レート制限は24時間で250件までなので、1日数件の運用なら十分余裕がある
- 楽天アフィリエイトの成果発生には、実際にクリックされた商品が24時間以内に購入される必要がある(楽天の仕様)
- 生成される投稿文はテンプレートベース。反応を見ながら `INTRO_PHRASES` や構成を継続的に改善していくことが、フォロワー・売上を伸ばす一番の近道
- `GH_PAT`(ローカルの`GITHUB_TOKEN`と共通)はSecrets/Issues/Contentsの書き換え権限を持つ強めのトークン。リポジトリ範囲を必ず該当リポジトリのみに絞ること
- 「投稿案を作る」処理はPCが起動している時間帯だけ動く。長期間PCを起動しないと、その間は新しい投稿案が作られない(承認済みの投稿の公開自体はクラウドで動き続ける)
- レビューIssueを放置して却下も承認もしないと、その回の投稿は行われないまま残り続ける。定期的にIssues一覧を確認すること
- `【PR】`表記・`#PR`ハッシュタグは景品表示法(ステルスマーケティング規制)対応の一般的なプラクティスとして組み込んでいるが、最終的な法令適合性の判断は必要に応じて専門家に確認すること
