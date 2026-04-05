"""現状 persona の不確実性が高い軸を狙って新問題を Claude headless で生成する.

不確実性駆動のアクティブラーニング:
    1. /api/persona から全回答を取得 → ベイズ推定
    2. (n_informed が少ない) or (std が高い) 軸を TOP N 抽出
    3. それらを主 loading に置く問題を Claude headless (`claude -p`) で生成
    4. validator で検証
    5. data/questions/questions.json に追記

Usage:
    export SWIPE_PERSONA_API_URL=https://swipe-persona-api.y-fudo.workers.dev
    export SWIPE_PERSONA_API_TOKEN=<sha256-hash>

    # デフォルト: 不確実性TOP10軸を狙って20問生成
    uv run python analysis/scripts/generate_targeted_questions.py

    # パラメータ指定
    uv run python analysis/scripts/generate_targeted_questions.py --count 30 --top-axes 15

    # プロンプトだけ出力して claude を呼ばない (手動実行用)
    uv run python analysis/scripts/generate_targeted_questions.py --print-prompt > prompt.txt

手動実行例:
    cat prompt.txt | claude -p > fragment.json
    uv run python analysis/scripts/generate_questions.py merge \\
        --fragment fragment.json --output data/questions/questions.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bayes_irt import (  # noqa: E402
    Answer,
    estimate_persona,
    load_axes,
    load_questions,
)


def fetch_answers(api_url: str, token: str) -> list[Answer]:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/persona",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "swipe-persona-updater/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
        payload = json.loads(res.read().decode("utf-8"))
    return [
        Answer(question_id=a["question_id"], response=int(a["response"]))
        for a in payload["answers"]
    ]


def rank_uncertain_axes(persona, axes, top_n: int) -> list:
    """不確実性の高い軸を TOP N 返す.

    スコア = std * 1.0 + max(0, 5 - n_informed) * 0.15
    (n が少ない軸を優先しつつ、n が十分でも std 高い軸も拾う)
    """
    rows = []
    for axis in axes:
        info = persona.axes[axis.axis_id]
        score = info["std"] + max(0, 5 - info["n_informed"]) * 0.15
        rows.append((score, axis, info))
    rows.sort(key=lambda r: -r[0])
    return rows[:top_n]


def build_prompt(uncertain_rows, axes_all, existing_ids: set[str], count: int) -> str:
    """Claude に渡す生成指示プロンプトを組み立てる."""
    target_axis_list = []
    for _score, axis, info in uncertain_rows:
        target_axis_list.append(
            f"- `{axis.axis_id}` ({axis.category}, 現在 mean={info['mean']:+.2f} "
            f"std={info['std']:.2f} n={info['n_informed']}): "
            f"{axis.display_name} / low={axis.pole_low} / high={axis.pole_high}"
        )

    # 既存軸一覧 (副軸として使うため、idとdisplay_nameのみ)
    all_axis_summary = "\n".join(
        f"- `{a.axis_id}`: {a.display_name}" for a in axes_all
    )

    sample_id_prefix = "q_targeted"
    existing_count = sum(1 for i in existing_ids if i.startswith(sample_id_prefix))
    start_num = existing_count + 1

    return f"""あなたは swipe-persona プロジェクトの問題生成担当です。

## 背景
Tinder式スワイプUI で湧心くん(ユーザー) がパーソナリティ質問に右(+1)/左(-1)/上(0)でスワイプし、
ベイズ多次元IRTで145軸のパーソナリティベクトルを推定するツール。既存問題プール 407問に対し、
**現在最も不確実性が高い軸**を狙って新問題 {count}問を追加生成してください。

## 狙い撃ちすべき軸 ({len(uncertain_rows)}軸)

以下の軸を**主loading**に置く問題を生成してください。これらは現状の推定で std が高いか
n_informed が少なく、確証が弱い軸です:

{chr(10).join(target_axis_list)}

## 全145軸 (副loading として利用可)

{all_axis_summary}

## 生成ルール

1. **{count}問**ちょうど生成
2. 各問は **主軸(上記TOP軸から)を1-2個 + 副軸(任意の軸から)を1-3個**、計 2-5軸 の loadings を持つ
3. **主軸の loading**: 0.5〜0.8 (符号は pole_high に近い方向なら +、pole_low に近い方向なら -)
4. **副軸の loading**: 0.2〜0.4
5. 質問文は具体的な日本語日常シーン、または Claude/AI 対話シーンで書く (抽象的性格問診は禁止)
6. 右スワイプ = YES の方向が文面から一意に読めること
7. question_id は `q_targeted_{start_num:03d}` から `q_targeted_{start_num + count - 1:03d}`
8. difficulty は -1.5〜+1.5 (基本 0.0)、discrimination は 1.0〜1.8 (基本 1.2)
9. **軸名は必ず上の軸リストに存在するもの**。タイポ禁止。

## 出力形式

**JSON配列のみ** を出力。前後に説明文や ```json ``` マーカーを付けない。
標準出力に JSON 配列だけ吐き出すこと。

```
[
  {{
    "question_id": "q_targeted_{start_num:03d}",
    "text": "具体的なシーン描写...",
    "loadings": {{
      "axis_id_1": 0.7,
      "axis_id_2": 0.3
    }},
    "difficulty": 0.0,
    "discrimination": 1.2
  }},
  ...
]
```

{count}問、JSON配列のみで返してください。
"""


def call_claude_headless(prompt: str) -> str:
    """claude -p で headless 実行して stdout を取得."""
    result = subprocess.run(  # noqa: S603
        ["claude", "-p", prompt],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr}")
    return result.stdout


def extract_json_array(raw: str) -> list:
    """Claude の出力から JSON 配列を抽出する (```json マーカーが付く場合もある)."""
    s = raw.strip()
    # ```json ... ``` を剥がす
    if s.startswith("```"):
        lines = s.split("\n")
        # 最初の ``` 行を除外
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 最後の ``` 行を除外
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    # 先頭に `[` がなければ、最初の `[` から最後の `]` までを抽出
    if not s.startswith("["):
        start = s.find("[")
        end = s.rfind("]")
        if start >= 0 and end > start:
            s = s[start : end + 1]
    return json.loads(s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent.parent.parent
    parser.add_argument("--questions", default=str(here / "data/questions/questions.json"))
    parser.add_argument("--axes", default=str(here / "data/axes/axes.yaml"))
    parser.add_argument("--count", type=int, default=20, help="生成する問題数")
    parser.add_argument("--top-axes", type=int, default=10, help="狙う軸の数")
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="プロンプトを stdout に出して終了 (claude呼ばない)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="生成のみ行い questions.json への追記はしない",
    )
    args = parser.parse_args()

    api_url = os.environ.get("SWIPE_PERSONA_API_URL")
    token = os.environ.get("SWIPE_PERSONA_API_TOKEN")
    if not api_url or not token:
        print("ERROR: SWIPE_PERSONA_API_URL と SWIPE_PERSONA_API_TOKEN を設定してください", file=sys.stderr)
        return 2

    print("fetching answers & running estimation...", file=sys.stderr)
    answers = fetch_answers(api_url, token)
    axes = load_axes(args.axes)
    questions = load_questions(args.questions)
    persona = estimate_persona(answers, questions, axes, prior_std=1.0)

    uncertain = rank_uncertain_axes(persona, axes, args.top_axes)
    print(f"=== 狙い撃ちする軸 TOP {args.top_axes} ===", file=sys.stderr)
    for score, axis, info in uncertain:
        print(
            f"  [{score:.2f}] {axis.axis_id:35} std={info['std']:.2f} n={info['n_informed']}",
            file=sys.stderr,
        )

    existing_ids = {q.question_id for q in questions}
    prompt = build_prompt(uncertain, axes, existing_ids, args.count)

    if args.print_prompt:
        print(prompt)
        return 0

    print(f"\ncalling claude -p to generate {args.count} questions...", file=sys.stderr)
    raw = call_claude_headless(prompt)

    try:
        new_questions = extract_json_array(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: could not parse JSON: {e}", file=sys.stderr)
        print("--- raw output ---", file=sys.stderr)
        print(raw[:2000], file=sys.stderr)
        return 3

    print(f"  generated {len(new_questions)} questions", file=sys.stderr)

    if args.dry_run:
        # fragment として書き出すだけ
        frag_path = here / "data/questions/fragments" / "targeted_dryrun.json"
        frag_path.parent.mkdir(parents=True, exist_ok=True)
        frag_path.write_text(
            json.dumps(new_questions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  dry-run: wrote {frag_path}", file=sys.stderr)
        return 0

    # questions.json にマージ
    qpath = Path(args.questions)
    existing = json.loads(qpath.read_text(encoding="utf-8"))
    by_id = {q["question_id"]: q for q in existing}
    added = 0
    for q in new_questions:
        if q["question_id"] not in by_id:
            existing.append(q)
            by_id[q["question_id"]] = q
            added += 1
    qpath.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"added {added} new questions; total={len(existing)}", file=sys.stderr)
    print(
        "\n次のステップ:\n"
        "  1. uv run python analysis/scripts/validate_questions.py で検証\n"
        "  2. cd worker && npx wrangler deploy で Worker を再デプロイ\n"
        "  3. ブラウザで新問題に回答\n"
        "  4. uv run python analysis/scripts/update_persona.py で persona 更新",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
