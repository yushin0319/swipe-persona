"""問題プール JSON を検証する.

チェック項目:
    1. question_id が重複していない
    2. loadings の axis_id が axes.yaml に存在する
    3. loadings が空でない (どの軸にも影響しない質問は無意味)
    4. discrimination > 0
    5. |loading| が 0.2 以上 (スパース表現前提)
    6. 各軸の平均 loading 絶対値が 0.1〜0.5 に収まる (スケールドリフト検出)
    7. 各軸が少なくとも 1問には登場する (カバレッジ)

Usage:
    uv run python analysis/scripts/validate_questions.py \
        [--questions data/questions/questions.json] \
        [--axes data/axes/axes.yaml]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def load_axes(path: Path) -> set[str]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {a["axis_id"] for a in data["axes"]}


def load_questions(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(questions: list[dict], known_axes: set[str]) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 重複
    ids = [q.get("question_id") for q in questions]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"duplicate question_id: {sorted(dup)}")

    # 軸ごとの loading 絶対値を集計
    per_axis: dict[str, list[float]] = defaultdict(list)

    for q in questions:
        qid = q.get("question_id", "<missing>")

        # 基本フィールド
        if "text" not in q or not q["text"]:
            errors.append(f"{qid}: text が空")
        loadings = q.get("loadings", {})
        if not loadings:
            errors.append(f"{qid}: loadings が空")
            continue

        disc = q.get("discrimination", 1.0)
        if disc <= 0:
            errors.append(f"{qid}: discrimination が 0 以下 ({disc})")

        # loadings 検証
        for axis_id, w in loadings.items():
            if axis_id not in known_axes:
                errors.append(f"{qid}: 未知の軸 '{axis_id}'")
                continue
            if abs(w) < 0.2:
                warnings.append(f"{qid}: loading {axis_id}={w:.2f} が弱すぎる (0.2 未満)")
            if abs(w) > 1.0:
                errors.append(f"{qid}: loading {axis_id}={w:.2f} が範囲外 (|w|>1.0)")
            per_axis[axis_id].append(abs(w))

    # 6. 軸ごとの平均 loading 絶対値
    for axis_id, ws in per_axis.items():
        avg = sum(ws) / len(ws)
        if avg < 0.1:
            warnings.append(f"axis '{axis_id}': 平均 |loading|={avg:.3f} が低すぎる")
        elif avg > 0.5:
            warnings.append(
                f"axis '{axis_id}': 平均 |loading|={avg:.3f} が高すぎる (ドリフトの疑い)"
            )

    # 7. カバレッジ: axes.yaml にあるが一度も登場しない軸
    uncovered = known_axes - per_axis.keys()
    if uncovered:
        warnings.append(f"未カバー軸 ({len(uncovered)}個): {sorted(uncovered)[:10]}...")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent.parent.parent
    parser.add_argument("--questions", default=here / "data/questions/questions.json")
    parser.add_argument("--axes", default=here / "data/axes/axes.yaml")
    args = parser.parse_args()

    qpath = Path(args.questions)
    apath = Path(args.axes)

    if not apath.exists():
        print(f"ERROR: axes file not found: {apath}", file=sys.stderr)
        return 2

    known_axes = load_axes(apath)

    if not qpath.exists():
        print(f"WARN: questions file not found: {qpath} (まだ生成されていない)")
        return 0

    questions = load_questions(qpath)
    errors, warnings = validate(questions, known_axes)

    print(f"Validated {len(questions)} questions against {len(known_axes)} axes")
    print(f"  errors:   {len(errors)}")
    print(f"  warnings: {len(warnings)}")
    for e in errors:
        print(f"  [ERROR] {e}")
    for w in warnings:
        print(f"  [WARN]  {w}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
