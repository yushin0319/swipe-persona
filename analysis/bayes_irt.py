"""ベイズ多次元 IRT コア.

モデル:
    θ ∈ R^K : 各軸の潜在値 (K = 105 軸想定)
    prior: N(0, σ0² I)
    質問 i:
        loading l_i ∈ R^K  (sparse, axes.yaml の軸に対応)
        discrimination a_i  (識別力, IRT の a パラメータ)
        difficulty    b_i  (困難度, IRT の b パラメータ)
    応答モデル (2PL IRT):
        z_i = a_i · (l_i · θ) - b_i
        P(回答=+1 | θ) = σ(z_i)
        P(回答=-1 | θ) = 1 - σ(z_i)
        回答=0 (SKIP) は尤度に寄与しない

事後推定:
    log p(θ | D) ∝ -||θ||² / (2 σ0²)
                     + Σ_i [y_i · log σ(z_i) + (1 - y_i) · log(1 - σ(z_i))]
    (y_i = 1 if response=+1, 0 if response=-1)

Laplace 近似:
    1. Newton 法で MAP 推定値 μ を求める
    2. ヘッセ行列 H の負逆行列を事後共分散 Σ = (-H)^{-1} とする
    3. 各軸の事後平均と標準偏差を出力

CLI:
    python bayes_irt.py estimate --answers answers.json --questions questions.json \
        --axes axes.yaml [--output out.md]

    python bayes_irt.py --json-io  # stdin に {"answers":[...], ...} を与え stdout に JSON
"""

from __future__ import annotations

import argparse
import json
import sys

# Windows の cp932 stdout で日本語が落ちないように UTF-8 化
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

# ==================== データクラス ====================


@dataclass
class Axis:
    axis_id: str
    category: str
    display_name: str
    description: str
    pole_low: str
    pole_high: str


@dataclass
class Question:
    question_id: str
    text: str
    loadings: dict[str, float]  # axis_id -> loading weight
    difficulty: float = 0.0
    discrimination: float = 1.0


@dataclass
class Answer:
    question_id: str
    response: int  # +1 (YES), -1 (NO), 0 (SKIP)


@dataclass
class PersonaVector:
    axes: dict[str, dict[str, float]] = field(default_factory=dict)
    # {axis_id: {"mean": float, "std": float, "n_informed": int}}


# ==================== 数値ユーティリティ ====================


def sigmoid(x):
    """数値的に安定なシグモイド."""
    x = np.asarray(x, dtype=float)
    # 大きな正値・負値でオーバーフロー回避
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    neg = ~pos
    exp_x = np.exp(x[neg])
    out[neg] = exp_x / (1.0 + exp_x)
    if out.ndim == 0:
        return float(out)
    return out


# ==================== ロード関数 ====================


def load_axes(path: str | Path) -> list[Axis]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [
        Axis(
            axis_id=a["axis_id"],
            category=a["category"],
            display_name=a["display_name"],
            description=a.get("description", ""),
            pole_low=a.get("pole_low", ""),
            pole_high=a.get("pole_high", ""),
        )
        for a in data["axes"]
    ]


def load_questions(path: str | Path) -> list[Question]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        Question(
            question_id=q["question_id"],
            text=q["text"],
            loadings=q["loadings"],
            difficulty=q.get("difficulty", 0.0),
            discrimination=q.get("discrimination", 1.0),
        )
        for q in data
    ]


def load_answers(path: str | Path) -> list[Answer]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [Answer(question_id=a["question_id"], response=int(a["response"])) for a in data]


# ==================== 推定コア ====================


def _build_design_matrix(
    answers: list[Answer],
    questions: list[Question],
    axis_index: dict[str, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """有効な回答のみを拾って IRT パラメータ行列を作る.

    Returns:
        L: shape (N, K) — 各有効回答の loading ベクトル × discrimination
        b: shape (N,) — 各有効回答の difficulty
        y: shape (N,) — 各有効回答の二値応答 (1 if +1, 0 if -1)
        axis_informed_counts: shape (K,) — 各軸が何回情報を得たか
    """
    K = len(axis_index)
    q_by_id = {q.question_id: q for q in questions}
    rows_L: list[np.ndarray] = []
    rows_b: list[float] = []
    rows_y: list[int] = []
    informed = np.zeros(K, dtype=int)

    for ans in answers:
        if ans.response == 0:
            continue  # SKIP は寄与しない
        q = q_by_id.get(ans.question_id)
        if q is None:
            continue  # 未知の質問は無視
        row = np.zeros(K, dtype=float)
        any_axis_matched = False
        for axis_id, w in q.loadings.items():
            idx = axis_index.get(axis_id)
            if idx is None:
                continue  # 未知の軸は無視
            row[idx] = w * q.discrimination
            informed[idx] += 1
            any_axis_matched = True
        if not any_axis_matched:
            continue  # この質問はどの軸にも寄与しない
        rows_L.append(row)
        rows_b.append(q.difficulty)
        rows_y.append(1 if ans.response > 0 else 0)

    if not rows_L:
        return np.zeros((0, K)), np.zeros(0), np.zeros(0), informed

    return (
        np.vstack(rows_L),
        np.array(rows_b, dtype=float),
        np.array(rows_y, dtype=float),
        informed,
    )


def _map_estimate(
    L: np.ndarray,
    b: np.ndarray,
    y: np.ndarray,
    prior_std: float,
    K: int,
    max_iter: int = 50,
    tol: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Newton 法で MAP 推定値 θ と事後共分散 Σ を求める.

    log posterior (up to const):
        -||θ||²/(2 σ0²) + Σ_i [y_i log σ(z_i) + (1 - y_i) log(1 - σ(z_i))]
        z_i = L_i · θ - b_i

    gradient:
        -θ/σ0² + Σ_i (y_i - σ(z_i)) · L_i

    Hessian:
        -I/σ0² - Σ_i σ(z_i)(1 - σ(z_i)) · L_i L_i^T
    """
    theta = np.zeros(K)
    prior_prec = 1.0 / (prior_std * prior_std)

    if L.shape[0] == 0:
        # 回答なし: 事前分布そのまま
        cov = np.eye(K) * (prior_std * prior_std)
        return theta, cov

    for _ in range(max_iter):
        z = L @ theta - b
        p = sigmoid(z)
        # 勾配
        grad = -prior_prec * theta + L.T @ (y - p)
        # ヘッセ行列 (対数事後の二階微分)
        w = p * (1.0 - p)  # shape (N,)
        # -I/σ0² - L^T diag(w) L
        H = -prior_prec * np.eye(K) - (L.T * w) @ L
        # Newton ステップ: θ_new = θ - H^{-1} · grad
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        theta_new = theta - step
        if np.max(np.abs(theta_new - theta)) < tol:
            theta = theta_new
            break
        theta = theta_new

    # 事後共分散: Σ = (-H)^{-1}
    z = L @ theta - b
    p = sigmoid(z)
    w = p * (1.0 - p)
    neg_H = prior_prec * np.eye(K) + (L.T * w) @ L
    try:
        cov = np.linalg.inv(neg_H)
    except np.linalg.LinAlgError:
        cov = np.eye(K) * (prior_std * prior_std)

    return theta, cov


def estimate_persona(
    answers: list[Answer],
    questions: list[Question],
    axes: list[Axis],
    prior_std: float = 1.0,
) -> PersonaVector:
    """回答からパーソナリティベクトルを推定する本体."""
    axis_index = {a.axis_id: i for i, a in enumerate(axes)}
    K = len(axis_index)
    L, b, y, informed = _build_design_matrix(answers, questions, axis_index)
    theta, cov = _map_estimate(L, b, y, prior_std, K=K)
    stds = np.sqrt(np.clip(np.diag(cov), 0.0, None))

    result = PersonaVector()
    for axis in axes:
        i = axis_index[axis.axis_id]
        result.axes[axis.axis_id] = {
            "mean": float(theta[i]),
            "std": float(stds[i]),
            "n_informed": int(informed[i]),
        }
    return result


# ==================== 出力 ====================


def format_markdown(persona: PersonaVector, axes: list[Axis]) -> str:
    """Claude 向け markdown を生成する."""
    lines: list[str] = []
    lines.append("# パーソナリティベクトル (swipe-persona)")
    lines.append("")
    lines.append("各軸の値は -1.0〜+1.0 の連続値。事前分布 N(0, 1.0²) からの事後推定。")
    lines.append("")

    # カテゴリごとにグルーピング
    by_category: dict[str, list[Axis]] = {}
    for axis in axes:
        by_category.setdefault(axis.category, []).append(axis)

    for category, category_axes in by_category.items():
        lines.append(f"## {category}")
        lines.append("")
        # 確信度の高い順 (std が小さい順) にソート
        ranked = sorted(
            category_axes,
            key=lambda a: persona.axes[a.axis_id]["std"],
        )
        for axis in ranked:
            info = persona.axes[axis.axis_id]
            mean = info["mean"]
            std = info["std"]
            n = info["n_informed"]
            interp = _interpret(mean, axis) if n > 0 else "(情報なし)"
            lines.append(f"- **{axis.display_name}**: {mean:+.2f} ± {std:.2f} (n={n}) — {interp}")
        lines.append("")

    return "\n".join(lines)


def _interpret(mean: float, axis: Axis) -> str:
    if mean >= 0.5:
        return f"強く {axis.pole_high}"
    if mean >= 0.2:
        return f"やや {axis.pole_high}"
    if mean <= -0.5:
        return f"強く {axis.pole_low}"
    if mean <= -0.2:
        return f"やや {axis.pole_low}"
    return "中立"


def persona_to_dict(persona: PersonaVector) -> dict[str, Any]:
    return {"axes": persona.axes}


# ==================== CLI ====================


def cmd_estimate(args: argparse.Namespace) -> int:
    axes = load_axes(args.axes)
    questions = load_questions(args.questions)
    answers = load_answers(args.answers)
    persona = estimate_persona(answers, questions, axes, prior_std=args.prior_std)
    md = format_markdown(persona, axes)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(md)
    return 0


def cmd_json_io(args: argparse.Namespace) -> int:
    """stdin JSON → stdout JSON. n8n や他プロセスからの呼び出し用."""
    payload = json.load(sys.stdin)
    axes = load_axes(payload["axes_path"])
    questions = load_questions(payload["questions_path"])
    answers = [Answer(**a) for a in payload["answers"]]
    prior_std = float(payload.get("prior_std", 1.0))
    persona = estimate_persona(answers, questions, axes, prior_std=prior_std)
    output = persona_to_dict(persona)
    output["markdown"] = format_markdown(persona, axes)
    json.dump(output, sys.stdout, ensure_ascii=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bayesian multidimensional IRT for swipe-persona")
    sub = parser.add_subparsers(dest="cmd")

    est = sub.add_parser("estimate", help="推定を実行して markdown 出力")
    est.add_argument("--answers", required=True, help="回答 JSON (List[{question_id, response}])")
    est.add_argument("--questions", required=True, help="問題プール JSON")
    est.add_argument("--axes", required=True, help="軸定義 YAML")
    est.add_argument("--prior-std", type=float, default=1.0)
    est.add_argument("--output", help="出力 markdown パス (省略時 stdout)")
    est.set_defaults(func=cmd_estimate)

    jio = sub.add_parser("json-io", help="stdin/stdout JSON モード")
    jio.set_defaults(func=cmd_json_io)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
