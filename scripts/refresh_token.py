import os
import subprocess

import requests

THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]

REFRESH_ENDPOINT = "https://graph.threads.net/refresh_access_token"


def refresh_token():
    resp = requests.get(
        REFRESH_ENDPOINT,
        params={
            "grant_type": "th_refresh_token",
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=15,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def update_github_secret(new_token):
    # gh CLI が GH_PAT (repo の secrets 書き込み権限を持つPAT) で認証済みである前提
    subprocess.run(
        ["gh", "secret", "set", "THREADS_ACCESS_TOKEN", "--body", new_token],
        check=True,
    )


def main():
    new_token = refresh_token()
    update_github_secret(new_token)
    print("THREADS_ACCESS_TOKEN を更新しました")


if __name__ == "__main__":
    main()
