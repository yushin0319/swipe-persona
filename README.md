# swipe-persona

Tinder 式スワイプ UI で無意識の好みを大量収集し、ベイズ多次元 IRT で 105 軸のパーソナリティベクトルを推定。Claude 用 markdown コンテキストとして出力するアプリ。

## コンセプト

- 入力は swipe の 3 値（右=+1 YES / 左=-1 NO / 上=0 SKIP）のみ
- 1 問が複数軸に重み付き（loadings）で影響し、1 回答で複数軸を同時更新
- ベイズ更新（Laplace 近似）で全軸の推定値と不確実性（共分散行列）を保持
- 自由記述なし、純粋数理のみで全貌を把握

## モノレポ構成

```
frontend/    React SPA (Vite + Tailwind v4) — スワイプ UI
analysis/    Python (numpy) — ベイズ IRT 推定・問題生成・validator
data/
  axes/axes.yaml               105 軸定義
  questions/questions.json     問題プール（loadings 付き）
```

n8n API ワークフローは別リポ [n8n-server](https://github.com/yushin0319/n8n-server) に追加（`swipe-persona-*.json`）。

## クイックスタート

### フロント開発サーバー
```bash
cd frontend && npm install && npm run dev
```

### ベイズ推定（CLI）
```bash
cd analysis
uv sync
uv run python bayes_irt.py estimate \
  --answers sample_answers.json \
  --questions ../data/questions/questions.json \
  --axes ../data/axes/axes.yaml
```

### 問題プール検証
```bash
uv run python analysis/scripts/validate_questions.py
```

### テスト
```bash
cd analysis && uv run pytest
cd frontend && npm test
```

## 数理モデル

2PL IRT ベース:

```
z_i = a_i · (l_i · θ) - b_i
P(回答=+1 | θ) = σ(z_i)
```

事後分布を Laplace 近似:

```
log p(θ | D) ∝ -||θ||²/(2σ₀²) + Σ_i [y_i log σ(z_i) + (1-y_i) log(1-σ(z_i))]
```

Newton 法で MAP 推定値 μ を求め、ヘッセ行列の逆で事後共分散 Σ を算出。

## デプロイ

- フロント: GitHub Pages（自動ビルド）
- 推定: ローカル CLI（n8n サーバーに Python を入れない、1GB RAM 制約のため）

## ライセンス

Private. Personal tool for building a Claude persona context.
