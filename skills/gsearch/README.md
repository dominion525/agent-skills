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

### Claude Code に plugin install した状態（推奨）

`<plugin-root>/bin` が PATH に乗るので `gsearch` コマンドが直接叩ける:

```bash
export GEMINI_API_KEY=<AI Studio キー>      # または GOOGLE_APPLICATION_CREDENTIALS=...
gsearch "<質問(自然文)>" [model]
```

### リポジトリをそのまま clone した場合（ローカル開発）

`node` で `search.js` を直接呼ぶ:

```bash
export GEMINI_API_KEY=<AI Studio キー>
node skills/gsearch/search.js "<質問(自然文)>" [model]
```

Vertex AI 経路の場合:

```bash
unset GEMINI_API_KEY
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
export GEMINI_LOCATION=us-central1   # 任意 (既定 us-central1)
node skills/gsearch/search.js "<質問(自然文)>" [model]
```

### モデル

- 既定モデルは経路ごとに分かれている。AI Studio 経路は `gemini-3.5-flash`、Vertex AI 経路は `gemini-2.5-flash`（Vertex AI 側に `gemini-3.5-flash` が存在しないため）
- 第 2 引数または `GEMINI_MODEL` env で上書きできる

```bash
GEMINI_MODEL=gemini-2.5-flash gsearch "..."
```

## 出力

回答 → Gemini が自動生成した検索クエリ → ソースURL。所要 ~15〜20秒。
詳細は `skills/gsearch/SKILL.md` を参照。
