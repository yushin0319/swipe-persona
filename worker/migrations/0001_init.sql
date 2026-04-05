-- swipe-persona 回答DB 初期スキーマ
--
-- answers:
--   question_id ごとに1レコード。同じ質問を再回答したら UPDATE で上書き (INSERT OR REPLACE)。
--   ベイズ推定では最新の回答のみを使うので履歴は不要。
--
-- sessions:
--   将来的にセッション単位の分析・ロールバック用に残すが、MVP では使わない。

CREATE TABLE IF NOT EXISTS answers (
  question_id TEXT PRIMARY KEY,
  response INTEGER NOT NULL CHECK (response IN (-1, 0, 1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_answers_updated_at ON answers(updated_at DESC);
