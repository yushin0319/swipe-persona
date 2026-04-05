# swipe-persona analysis scripts

## セットアップ

```bash
export SWIPE_PERSONA_API_URL=https://swipe-persona-api.y-fudo.workers.dev
export SWIPE_PERSONA_API_TOKEN=<ブラウザの localStorage から取れる SHA-256 ハッシュ>
```

## 日常運用フロー

### 1. 隙間時間に回答を追加する

https://yushin0319.github.io/swipe-persona/ で未回答問題をスワイプ。D1 に自動保存される。

### 2. persona を最新化する (`update_persona.py`)

```bash
cd swipe-persona
uv run --project analysis python analysis/scripts/update_persona.py
```

動作:
- Worker API から全回答を fetch
- bayes_irt で 145軸を推定
- `~/.claude/personas/yushin.md` に書き出し (Claude セッション開始時に参照される)
- `analysis/real_persona.md` にもコピー (リポ内ローカル、.gitignore 済)
- 確信度の高い軸 TOP10 を stderr に表示

### 3. 不確実性の高い軸を狙った新問題を生成する (`generate_targeted_questions.py`)

```bash
# 不確実性 TOP10 軸を狙って 20問追加
uv run --project analysis python analysis/scripts/generate_targeted_questions.py

# 軸数と問題数を指定
uv run --project analysis python analysis/scripts/generate_targeted_questions.py --top-axes 15 --count 30

# プロンプトだけ出力 (手動で claude -p に流したいとき)
uv run --project analysis python analysis/scripts/generate_targeted_questions.py --print-prompt > prompt.txt
cat prompt.txt | claude -p > fragment.json

# ドライラン (生成は行うが questions.json には追記しない)
uv run --project analysis python analysis/scripts/generate_targeted_questions.py --dry-run
```

動作:
- 現在 persona を再計算
- std が高い・n が少ない軸 TOP N を抽出
- Claude headless (`claude -p`) に問題生成を依頼
- 返ってきた JSON を `data/questions/questions.json` にマージ

### 4. 新問題の検証とデプロイ

```bash
uv run --project analysis python analysis/scripts/validate_questions.py
cd worker && npx wrangler deploy
```

### 5. ループを回す

```
① スワイプで回答 → ② update_persona.py → ③ generate_targeted_questions.py
→ ④ validator + wrangler deploy → ①に戻る
```

不確実性の高い軸が優先的に埋まっていくので、同じ問題を繰り返さずに効率的に推定精度が上がる。

## トラブルシュート

- `urllib.error.HTTPError: 403`: Cloudflare WAF が Python の default User-Agent を弾く。スクリプトは `swipe-persona-updater/1.0` を送るので通常は問題ないが、まだ出る場合は `--header "User-Agent: curl/8.0"` を追加
- `claude -p` が見つからない: `claude` CLI (Claude Code) がインストールされていて PATH に通っている必要あり
- JSON パース失敗: `--dry-run` でまず確認し、Claude の出力形式が崩れている場合はプロンプトを調整
