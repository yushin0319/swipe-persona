"""ベイズ多次元 IRT コアのテスト.

モデル:
    θ ∈ R^K, prior N(0, σ0² I)
    質問 i: loading l_i ∈ R^K (sparse), discrimination a_i, difficulty b_i
    P(回答=+1 | θ) = σ(a_i · (l_i · θ) - b_i)
    Laplace近似で事後 N(μ_post, Σ_post) を推定
"""

import numpy as np
import pytest

from bayes_irt import (
    Answer,
    Axis,
    Question,
    estimate_persona,
    format_markdown,
    sigmoid,
)


@pytest.fixture
def simple_axes():
    # 3軸のミニマル構成
    return [
        Axis(axis_id="openness", category="bigfive", display_name="開放性",
             description="", pole_low="", pole_high=""),
        Axis(axis_id="extraversion", category="bigfive", display_name="外向性",
             description="", pole_low="", pole_high=""),
        Axis(axis_id="analytical", category="cognitive", display_name="分析的",
             description="", pole_low="", pole_high=""),
    ]


@pytest.fixture
def simple_questions():
    # 質問1: openness に強く影響 (右スワイプ = 開放性が高い)
    # 質問2: extraversion に強く影響
    # 質問3: analytical に強く影響
    return [
        Question(question_id="q1", text="新しい芸術を試す",
                 loadings={"openness": 0.9}, difficulty=0.0, discrimination=1.5),
        Question(question_id="q2", text="人と会うのが好き",
                 loadings={"extraversion": 0.9}, difficulty=0.0, discrimination=1.5),
        Question(question_id="q3", text="論理的に考える",
                 loadings={"analytical": 0.9}, difficulty=0.0, discrimination=1.5),
    ]


def test_sigmoid_basic():
    assert sigmoid(0.0) == pytest.approx(0.5)
    assert sigmoid(100.0) == pytest.approx(1.0, abs=1e-6)
    assert sigmoid(-100.0) == pytest.approx(0.0, abs=1e-6)


def test_sigmoid_numerically_stable():
    # overflow しないこと
    result = sigmoid(np.array([1000.0, -1000.0]))
    assert np.all(np.isfinite(result))


def test_estimate_with_no_answers_returns_prior(simple_axes, simple_questions):
    # 回答0件: prior (μ=0, σ=prior_std) が返る
    result = estimate_persona(answers=[], questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    for axis in simple_axes:
        assert result.axes[axis.axis_id]["mean"] == pytest.approx(0.0, abs=1e-3)
        assert result.axes[axis.axis_id]["std"] == pytest.approx(1.0, abs=1e-3)
        assert result.axes[axis.axis_id]["n_informed"] == 0


def test_single_answer_moves_relevant_axis(simple_axes, simple_questions):
    # q1 (openness) に +1 (YES) を回答 → openness の mean が正方向に動く
    answers = [Answer(question_id="q1", response=1)]
    result = estimate_persona(answers=answers, questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    assert result.axes["openness"]["mean"] > 0.1
    # 他の軸はほとんど動かない (loadings に含まれない)
    assert abs(result.axes["extraversion"]["mean"]) < 1e-3
    assert abs(result.axes["analytical"]["mean"]) < 1e-3
    # 情報量カウント
    assert result.axes["openness"]["n_informed"] == 1
    assert result.axes["extraversion"]["n_informed"] == 0


def test_negative_answer_moves_opposite_direction(simple_axes, simple_questions):
    # q1 (openness) に -1 (NO) → openness の mean が負方向に動く
    answers = [Answer(question_id="q1", response=-1)]
    result = estimate_persona(answers=answers, questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    assert result.axes["openness"]["mean"] < -0.1


def test_skip_does_not_update(simple_axes, simple_questions):
    # response=0 (SKIP) は更新に寄与しない
    answers = [Answer(question_id="q1", response=0)]
    result = estimate_persona(answers=answers, questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    assert result.axes["openness"]["mean"] == pytest.approx(0.0, abs=1e-3)
    assert result.axes["openness"]["n_informed"] == 0


def test_multiple_answers_reduce_uncertainty(simple_axes, simple_questions):
    # 同じ軸に複数回答 → std が小さくなる (不確実性が減る)
    single = [Answer(question_id="q1", response=1)]
    result_single = estimate_persona(answers=single, questions=simple_questions,
                                     axes=simple_axes, prior_std=1.0)

    # q1 と同じ軸に影響する追加質問
    extra_questions = [
        *simple_questions,
        Question(question_id="q4", text="抽象概念が好き",
                 loadings={"openness": 0.8}, difficulty=0.0, discrimination=1.5),
    ]
    multiple = [Answer(question_id="q1", response=1), Answer(question_id="q4", response=1)]
    result_multiple = estimate_persona(answers=multiple, questions=extra_questions,
                                       axes=simple_axes, prior_std=1.0)

    assert result_multiple.axes["openness"]["std"] < result_single.axes["openness"]["std"]
    assert result_multiple.axes["openness"]["n_informed"] == 2


def test_multi_axis_loading_updates_multiple_axes(simple_axes, simple_questions):
    # 1問で複数軸が同時更新されること (本モデルの核)
    multi_q = Question(
        question_id="q_multi",
        text="論理的な人々と一緒にいたい",
        loadings={"extraversion": 0.7, "analytical": 0.6},
        difficulty=0.0,
        discrimination=1.5,
    )
    questions = [*simple_questions, multi_q]
    answers = [Answer(question_id="q_multi", response=1)]
    result = estimate_persona(answers=answers, questions=questions,
                              axes=simple_axes, prior_std=1.0)
    assert result.axes["extraversion"]["mean"] > 0.05
    assert result.axes["analytical"]["mean"] > 0.05
    assert result.axes["openness"]["mean"] == pytest.approx(0.0, abs=1e-3)
    # 両軸がカウントされる
    assert result.axes["extraversion"]["n_informed"] == 1
    assert result.axes["analytical"]["n_informed"] == 1


def test_format_markdown_contains_all_axes(simple_axes, simple_questions):
    answers = [Answer(question_id="q1", response=1)]
    result = estimate_persona(answers=answers, questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    md = format_markdown(result, simple_axes)
    assert "開放性" in md
    assert "外向性" in md
    assert "分析的" in md
    # mean ± std 形式
    assert "±" in md


def test_unknown_question_id_in_answer_ignored(simple_axes, simple_questions):
    # 存在しない question_id は無視 (壊れない)
    answers = [Answer(question_id="q_unknown", response=1)]
    result = estimate_persona(answers=answers, questions=simple_questions,
                              axes=simple_axes, prior_std=1.0)
    for axis in simple_axes:
        assert result.axes[axis.axis_id]["mean"] == pytest.approx(0.0, abs=1e-3)


def test_unknown_axis_in_loading_ignored(simple_axes, simple_questions):
    # loading に未定義の軸があっても壊れない
    bad_q = Question(question_id="q_bad", text="bad",
                     loadings={"openness": 0.5, "nonexistent_axis": 0.9},
                     difficulty=0.0, discrimination=1.5)
    questions = [*simple_questions, bad_q]
    answers = [Answer(question_id="q_bad", response=1)]
    # 例外を投げず、未知軸は無視される
    result = estimate_persona(answers=answers, questions=questions,
                              axes=simple_axes, prior_std=1.0)
    assert result.axes["openness"]["mean"] > 0.05
