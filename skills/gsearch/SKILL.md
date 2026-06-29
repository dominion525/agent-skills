---
name: gsearch
description: >
  Use when the user explicitly asks to search Google or look something up on Google
  (e.g. says "Googleで調べて" / "Googleで検索して"). Runs a Gemini google_search grounded
  search: Gemini forms its own search queries, searches Google, and returns a grounded
  answer with the queries it used and source URLs. Invoke on request — not as an
  automatic replacement for the built-in WebSearch. Reuses GEMINI_API_KEY (AI Studio)
  or GOOGLE_APPLICATION_CREDENTIALS (Vertex AI SA key); no extra key, no MCP.
allowed-tools: Bash
---

# gsearch — Gemini(google_search) で web 検索

自然文の質問を投げると、**Gemini が自分で検索キーワードを組んで Google を検索**し、グラウンディングされた回答＋使った検索クエリ＋ソースURL を返す。内蔵 WebSearch の代替（品質・クエリ自動生成で優れる）。

## 前提
- node v18+（global fetch / webcrypto / AbortSignal.timeout を使う）。
- 認証情報を次のいずれかで env にセットする（**この skill はキーを保持しない**。env から読むだけ）:
  - `GEMINI_API_KEY` … AI Studio キー（優先される）。
  - `GOOGLE_APPLICATION_CREDENTIALS` … Vertex AI のサービスアカウント JSON のパス。
    - `PROJECT_ID` は SA キー JSON の `project_id` から自動取得する。
    - `GEMINI_LOCATION` でリージョン上書き（既定 `us-central1`）。
- 両方ある場合は AI Studio が優先される。両方未設定だとエラー終了する。

## 使い方
plugin install 経由なら `gsearch` コマンドが PATH に乗る:

```bash
gsearch "<検索したい質問(自然文でよい)>"
```

任意でモデルを第 2 引数に渡せる:

```bash
gsearch "<質問>" gemini-2.5-flash
```

- 質問は自然文でよい。検索キーワードは Gemini が咀嚼して自動で組む。
- 既定モデルは経路ごとに分けている。AI Studio 経路は `gemini-3.5-flash`、Vertex AI 経路は `gemini-2.5-flash`（Vertex AI 側に `gemini-3.5-flash` が存在しないため）。両方とも `GEMINI_MODEL` env または第 2 引数で上書きできる。
- 出力は stdout（回答 → Gemini が使った検索クエリ → ソースURL）。`tail` で切らず全文を扱う。
- 所要 ~15〜20秒（grounding のため）。タイムアウトは 60 秒に設定済み。Vertex AI 経路では追加で access token 取得 (約 1〜2 秒) が入る。

## 挙動
- Gemini API の google_search グラウンディングを**単発で1回**呼ぶ（ループしない）。
  - AI Studio 経路: tools `[{ google_search: {} }]`。
  - Vertex AI 経路: tools `[{ googleSearch: {} }]`（camelCase）。SA キー JSON から RS256 JWT を webcrypto で自前署名し、`oauth2.googleapis.com/token` で access token を交換する（外部 npm 依存なし）。
- ソースは grounding の redirect URL を実URLに解決して表示（best-effort）。

## いつ使うか
- **「Googleで調べて」等、ユーザーが明示的に Google 検索を求めたとき**に使う。
- 内蔵 WebSearch の自動全置換ではない。指示があったら本 skill で検索する。
- 用途: 最新情報・事実確認の web 検索、根拠付き回答、セカンドオピニオン。
