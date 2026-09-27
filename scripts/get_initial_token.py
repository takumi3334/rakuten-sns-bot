"""
初回だけ手動で実行するスクリプト。
Threadsの認可コード(code)を長期アクセストークンに交換し、
あわせてThreadsユーザーIDも取得する。

事前準備:
1. 下記の「認可URL」をブラウザで開き、ログイン・許可する
2. リダイレクト先URLの ?code=xxxx の部分(URLエンコードされた文字列。
   末尾に #_ が付くことがあるので、それは除いてコピー)を控える
3. このスクリプトを実行し、コピーした認可コードを引数として渡す

認可URLの組み立て方 (THREADS_APP_ID と REDIRECT_URI は自分の値に置き換える):
https://threads.net/oauth/authorize
  ?client_id=<THREADS_APP_ID>
  &redirect_uri=<REDIRECT_URI>
  &scope=threads_basic,threads_content_publish
  &response_type=code
"""

import os
import sys

import requests

THREADS_APP_ID = os.environ["THREADS_APP_ID"]
THREADS_APP_SECRET = os.environ["THREADS_APP_SECRET"]
REDIRECT_URI = os.environ["THREADS_REDIRECT_URI"]


def exchange_code_for_short_lived_token(code):
    resp = requests.post(
        "https://graph.threads.net/oauth/access_token",
        data={
            "client_id": THREADS_APP_ID,
            "client_secret": THREADS_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["user_id"]


def exchange_for_long_lived_token(short_lived_token):
    resp = requests.get(
        "https://graph.threads.net/access_token",
        params={
            "grant_type": "th_exchange_token",
            "client_secret": THREADS_APP_SECRET,
            "access_token": short_lived_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    if len(sys.argv) != 2:
        print("使い方: python scripts/get_initial_token.py <認可コード>")
        sys.exit(1)

    code = sys.argv[1]
    short_lived_token, user_id = exchange_code_for_short_lived_token(code)
    long_lived_token = exchange_for_long_lived_token(short_lived_token)

    print("\n=== 以下をGitHub Secretsに登録してください ===")
    print(f"THREADS_USER_ID = {user_id}")
    print(f"THREADS_ACCESS_TOKEN = {long_lived_token}")


if __name__ == "__main__":
    main()
