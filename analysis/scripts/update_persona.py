"""D1 から最新回答を fetch し、bayes_irt で推定、persona.md を更新する.

Usage:
    # 環境変数で API URL と token を指定
    export SWIPE_PERSONA_API_URL=https://swipe-persona-api.y-fudo.workers.dev
    export SWIPE_PERSONA_API_TOKEN=<sha256-hash>
    uv run python analysis/scripts/update_persona.py

    # ローカル配信先を変えたい場合 (デフォルト ~/.claude/personas/yushin.md)
    uv run python analysis/scripts/update_persona.py --local-path ~/path/to/persona.md

    # 特定の stdout ファイルにも書きたい場合
    uv run python analysis/scripts/update_persona.py --also-write analysis/real_persona.md

動作:
    1. Worker API の /api/persona から全回答を取得 (Bearer 認証)
    2. bayes_irt で 145軸を推定
    3. persona.md を生成して:
        - ~/.claude/personas/yushin.md にコピー (Claudeセッション開始時参照)
        - analysis/real_persona.md にも書く (リポ内ローカル、.gitignore 済)
    4. 概況 (答え済問題数、確信度の高い軸 TOP10) を stdout に出す
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _api_client import fetch_answers, get_api_env

from bayes_irt import (
    estimate_persona,
    format_markdown,
    load_axes,
    load_questions,
)

DEFAULT_LOCAL_PATH = "~/.claude/personas/yushin.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent.parent.parent
    parser.add_argument("--questions", default=str(here / "data/questions/questions.json"))
    parser.add_argument("--axes", default=str(here / "data/axes/axes.yaml"))
    parser.add_argument(
        "--local-path",
        default=DEFAULT_LOCAL_PATH,
        help="Claude セッションから参照する配信先 (デフォルト ~/.claude/personas/yushin.md)",
    )
    parser.add_argument(
        "--also-write",
        help="リポ内ローカルにも書きたい場合のパス (例: analysis/real_persona.md)",
    )
    parser.add_argument("--prior-std", type=float, default=1.0)
    args = parser.parse_args()

    api_url, token = get_api_env()

    print(f"fetching answers from {api_url}...", file=sys.stderr)
    answers = fetch_answers(api_url, token)
    print(f"  {len(answers)} answers fetched", file=sys.stderr)

    print("loading axes and questions...", file=sys.stderr)
    axes = load_axes(args.axes)
    questions = load_questions(args.questions)

    print("running bayes estimation...", file=sys.stderr)
    persona = estimate_persona(answers, questions, axes, prior_std=args.prior_std)
    md = format_markdown(persona, axes)

    # ローカル配信 (~/.claude/personas/yushin.md)
    local_path = Path(os.path.expanduser(args.local_path))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(md, encoding="utf-8")
    print(f"wrote {local_path}", file=sys.stderr)

    # 追加書き込み (リポ内ローカル等)
    if args.also_write:
        also = Path(args.also_write)
        also.parent.mkdir(parents=True, exist_ok=True)
        also.write_text(md, encoding="utf-8")
        print(f"wrote {also}", file=sys.stderr)

    # サマリー: std の小さい (確信度の高い) 軸 TOP10
    ranked = sorted(
        axes,
        key=lambda a: persona.axes[a.axis_id]["std"],
    )
    print("\n=== 確信度の高い軸 TOP 10 ===", file=sys.stderr)
    for axis in ranked[:10]:
        info = persona.axes[axis.axis_id]
        name = axis.display_name
        mean = info["mean"]
        std = info["std"]
        n = info["n_informed"]
        print(f"  {name:20} {mean:+.2f} ± {std:.2f} (n={n})", file=sys.stderr)

    total_answered = sum(1 for a in answers)
    print(f"\n回答済み: {total_answered} / {len(questions)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
