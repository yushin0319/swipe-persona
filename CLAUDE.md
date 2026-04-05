# swipe-persona

Tinder式スワイプUIで無意識の好みを大量収集し、ベイズ多次元IRTで105軸のパーソナリティベクトルを推定。Claude用markdownコンテキストとして出力するアプリ。

## コンセプト

- 入力は swipe の3値（右=+1 YES / 左=-1 NO / 上=0 SKIP）のみ
- 1問が複数軸に重み付き（loadings）で影響し、1回答で複数軸を同時更新
- ベイズ更新（Laplace近似）で全軸の推定値+不確実性（共分散行列）を保持
- 不確実性の高い軸を狙って新問題を補充（アクティブラーニング）
- 自由記述・コメント入力なし。純粋数理のみで全貌を把握

## ディレクトリ構成

```
frontend/       React SPA (Vite + Tailwind) — スワイプUI
analysis/       Python (numpy only) — ベイズIRT推定・問題生成・validator
  bayes_irt.py  推定コアCLI
  scripts/      generate_questions.py / validate_questions.py
  tests/        pytest
data/
  axes/axes.yaml          105軸定義（カテゴリ別）
  questions/questions.json 問題プール + loadings
```

n8n APIワークフローは別リポ `n8n-server` に追加（`swipe-persona-*.json`）。

## 数理モデル

- 各軸 θ_k ~ N(μ_k, σ_k²) のガウス事前
- IRT 2PL: `P(+1 | θ) = σ(a · Σ_k loading_k·θ_k - b)`
- Laplace近似で勾配＋ヘッセ行列から事後分布を更新
- scipy 不要、numpy のみで実装

## コマンド

```bash
# フロント開発サーバー
cd frontend && npm run dev

# ベイズ推定（CLIモード）
uv run python analysis/bayes_irt.py estimate \
  --answers data/session_001.json \
  --questions data/questions/questions.json \
  --axes data/axes/axes.yaml

# 問題生成（domain単位）
uv run python analysis/scripts/generate_questions.py --domain aesthetic --count 20

# 問題バリデータ
uv run python analysis/scripts/validate_questions.py

# テスト
cd analysis && uv run pytest
cd frontend && npm test
```

## テスト方針

- ベイズ推定ロジック: pytest（回答0件でPrior返却、既知セットで事後が動く等）
- React: vitest（SwipeCard の左右判定）
- E2Eはスコープ外

## デプロイ

- フロント: GitHub Pages
- 推定スクリプト: ローカル CLI（n8nサーバーにはPython入れない、1GB RAM制約）
- 将来: n8n から Python を呼び出すか、JS移植を検討
