# swipe-persona

Tinder 式スワイプ UI で無意識の好みを大量収集し、ベイズ多次元 IRT で 105 軸のパーソナリティベクトルを推定。Claude 用 markdown コンテキストとして出力するアプリ。

- **本番**: https://yushin0319.github.io/swipe-persona/

## コンセプト

- 入力は swipe の 3 値（右=+1 YES / 左=-1 NO / 上=0 SKIP）のみ
- 1 問が複数軸に重み付き（loadings）で影響し、1 回答で複数軸を同時更新
- ベイズ更新（Laplace 近似）で全軸の推定値と不確実性（共分散行列）を保持
- 自由記述なし、純粋数理のみで全貌を把握

## モノレポ構成

```
frontend/    React SPA（Vite + Tailwind v4）— スワイプ UI（GitHub Pages）
worker/      Cloudflare Workers API（swipe-persona-api、D1 + Sentry）
analysis/    Python（numpy）— ベイズ IRT 推定・問題生成・validator（ローカル CLI）
data/
  axes/axes.yaml               105 軸定義
  questions/questions.json     問題プール（loadings 付き）
```

n8n API ワークフローは別リポ [n8n-server](https://github.com/yushin0319/n8n-server) に追加（`swipe-persona-*.json`）。

## API（Cloudflare Workers `swipe-persona-api`）

すべて `Authorization: Bearer <sha256-hash>` で `AUTH_TOKEN_HASH` と timing-safe 比較（フロントの localStorage に保存したハッシュをそのまま渡す想定）。

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/questions?limit=N` | 未回答問題を最大 N 件返す（問題プールは Worker に埋め込み） |
| `POST` | `/api/answers` | 回答（`{question_id, response: -1\|0\|1}`）を D1 に保存 |
| `GET` | `/api/persona` | 全回答を返す（推定はローカル CLI で実行） |
| `GET` | `/health` | 死活 |

観測: Sentry（`@sentry/cloudflare`、release tag は CI で git SHA）/ observability-tail（`tail_consumers`）。

## 開発

### フロント

```bash
cd frontend && bun install && bun run dev
bun run build
bun test
```

### ベイズ推定（ローカル CLI）

```bash
cd analysis
uv sync
uv run python bayes_irt.py estimate \
  --answers sample_answers.json \
  --questions ../data/questions/questions.json \
  --axes ../data/axes/axes.yaml
uv run python scripts/validate_questions.py
uv run pytest
```

### Worker

```bash
cd worker && bun install
bunx wrangler dev --remote
bunx wrangler deploy
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

Newton 法で MAP 推定値 μ を求め、ヘッセ行列の逆で事後共分散 Σ を算出。`scipy` 不要、`numpy` のみで実装。

## デプロイ

- **フロント**: GitHub Pages（main push で自動）
- **Worker**: `bunx wrangler deploy`（D1 + KV）
- **推定**: ローカル CLI（n8n サーバーに Python 入れない、1GB RAM 制約）

## 運用ルール

- `AUTH_TOKEN_HASH` は `wrangler secret put` のみ。コードにコミットしない
- main 直 commit 禁止、PR 経由でマージ
- 観測: `tail-errors.py --since 24h --script swipe-persona-api`

## ライセンス

Private. Personal tool for building a Claude persona context.
