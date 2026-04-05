"""swipe-persona Worker API クライアント (update_persona / generate_targeted_questions 共通)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bayes_irt import Answer


def get_api_env() -> tuple[str, str]:
    """環境変数から API URL と token を取得。未設定ならエラー終了。"""
    api_url = os.environ.get("SWIPE_PERSONA_API_URL")
    token = os.environ.get("SWIPE_PERSONA_API_TOKEN")
    if not api_url or not token:
        print(
            "ERROR: SWIPE_PERSONA_API_URL と SWIPE_PERSONA_API_TOKEN を設定してください",
            file=sys.stderr,
        )
        sys.exit(2)
    return api_url, token


def fetch_answers(api_url: str, token: str) -> list[Answer]:
    """Worker /api/persona から全回答を取得する。

    Cloudflare WAF が Python の default User-Agent を弾くので明示。
    """
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/persona",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "swipe-persona-updater/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode("utf-8"))
    return [
        Answer(question_id=a["question_id"], response=int(a["response"]))
        for a in payload["answers"]
    ]
