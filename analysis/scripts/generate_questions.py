"""問題プール生成支援スクリプト.

このスクリプトは問題 JSON 断片を集約・マージするためのユーティリティ.
実際の問題テキスト + loadings の生成は Claude (headless or subagent) に任せ、
このスクリプトは生成された断片を受け取って本体 JSON に統合する役割.

Usage:
    # 単一断片をマージ
    uv run python analysis/scripts/generate_questions.py merge \
        --fragment fragment.json \
        --output data/questions/questions.json

    # ディレクトリ内の全断片を一括マージ
    uv run python analysis/scripts/generate_questions.py merge-dir \
        --input-dir data/questions/fragments/ \
        --output data/questions/questions.json

    # axes.yaml から各カテゴリの軸一覧を抽出 (サブエージェント用のブリーフィング生成)
    uv run python analysis/scripts/generate_questions.py spec \
        --category aesthetic \
        --axes data/axes/axes.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def cmd_merge(args: argparse.Namespace) -> int:
    fragment = json.loads(Path(args.fragment).read_text(encoding="utf-8"))
    if not isinstance(fragment, list):
        print("fragment must be a JSON array", file=sys.stderr)
        return 1
    out_path = Path(args.output)
    existing: list[dict] = []
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    merged = _merge(existing, fragment)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"merged {len(fragment)} new questions; total={len(merged)}")
    return 0


def cmd_merge_dir(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"input dir not found: {input_dir}", file=sys.stderr)
        return 1
    total_new: list[dict] = []
    for frag_path in sorted(input_dir.glob("*.json")):
        frag = json.loads(frag_path.read_text(encoding="utf-8"))
        total_new.extend(frag)
        print(f"  loaded {frag_path.name}: {len(frag)} questions")
    out_path = Path(args.output)
    existing: list[dict] = []
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    merged = _merge(existing, total_new)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"merged {len(total_new)} new questions; total={len(merged)}")
    return 0


def _merge(existing: list[dict], new: list[dict]) -> list[dict]:
    """既存リストに新規問題を追加. question_id の重複は新規側を優先."""
    by_id = {q["question_id"]: q for q in existing}
    for q in new:
        by_id[q["question_id"]] = q
    return list(by_id.values())


def cmd_spec(args: argparse.Namespace) -> int:
    axes = yaml.safe_load(Path(args.axes).read_text(encoding="utf-8"))["axes"]
    targets = [a for a in axes if a["category"] == args.category]
    if not targets:
        print(f"no axes found for category={args.category}", file=sys.stderr)
        return 1
    print(f"# Category: {args.category} ({len(targets)} axes)")
    for a in targets:
        print(f"- {a['axis_id']}: {a['display_name']}")
        print(f"  - low:  {a['pole_low']}")
        print(f"  - high: {a['pole_high']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    m = sub.add_parser("merge", help="単一断片をマージ")
    m.add_argument("--fragment", required=True)
    m.add_argument("--output", required=True)
    m.set_defaults(func=cmd_merge)

    md = sub.add_parser("merge-dir", help="ディレクトリ内の全断片を一括マージ")
    md.add_argument("--input-dir", required=True)
    md.add_argument("--output", required=True)
    md.set_defaults(func=cmd_merge_dir)

    s = sub.add_parser("spec", help="カテゴリ軸一覧を出力 (サブエージェント向け)")
    s.add_argument("--category", required=True)
    s.add_argument("--axes", required=True)
    s.set_defaults(func=cmd_spec)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
