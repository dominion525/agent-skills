# gsearch

Claude Code から Gemini API の Google Search グラウンディング（`google_search`）で web 検索する薄い skill。
内蔵 WebSearch の代替で、質問を Gemini が咀嚼して検索クエリを組み、根拠付き回答＋ソースを返す。

AI Studio キーでも Vertex AI のサービスアカウントでも動く。env で経路を自動判定する。

## 前提

- node v18+（global fetch / webcrypto / AbortSignal.timeout を使う）
- 外部 npm 依存なし
- 認証は env のいずれかを設定する（skill 自体はキーを保持しない）
  - `GEMINI_API_KEY` … AI Studio キー（こちらが優先される）
  - `GOOGLE_APPLICATION_CREDENTIALS` … Vertex AI のサービスアカウント JSON のパス

## 使い方

### AI Studio 経路

```bash
export GEMINI_API_KEY=<AI Studio キー>
node skills/gsearch/search.js "<質問(自然文)>" [model]
```

### Vertex AI 経路

```bash
unset GEMINI_API_KEY
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
export GEMINI_LOCATION=us-central1   # 任意 (既定 us-central1)
node skills/gsearch/search.js "<質問(自然文)>" [model]
```

- `PROJECT_ID` は SA キー JSON の `project_id` から取得する
- 既定モデルは `gemini-3.5-flash`。Vertex AI 側で同名が通らない場合は `GEMINI_MODEL` で上書きする
  例: `GEMINI_MODEL=gemini-2.5-flash node skills/gsearch/search.js "..."`

## 出力

回答 → Gemini が自動生成した検索クエリ → ソースURL。所要 ~15〜20秒。
詳細は `skills/gsearch/SKILL.md` を参照。
