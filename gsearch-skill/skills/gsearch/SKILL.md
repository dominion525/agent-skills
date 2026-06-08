---
name: gsearch
description: Use when the user explicitly asks to search Google or look something up on Google (e.g. says "Googleで調べて" / "Googleで検索して"). Runs a Gemini google_search grounded search: Gemini forms its own search queries, searches Google, and returns a grounded answer with the queries it used and source URLs. Invoke on request — not as an automatic replacement for the built-in WebSearch. Reuses GEMINI_API_KEY; no extra key, no MCP.
allowed-tools: Bash
---

# gsearch — Gemini(google_search) で web 検索

自然文の質問を投げると、**Gemini が自分で検索キーワードを組んで Google を検索**し、グラウンディングされた回答＋使った検索クエリ＋ソースURL を返す。内蔵 WebSearch の代替（品質・クエリ自動生成で優れる）。

## 前提
- 環境変数 `GEMINI_API_KEY` があること（**この skill はキーを保持しない**。env から読むだけ）。
- node v18+（fetch 内蔵）。

## 使い方
このディレクトリ同梱の `search.js` を実行する:

```bash
node "$HOME/src/sandbox/gsearch-skill/skills/gsearch/search.js" "<検索したい質問(自然文でよい)>"
```

- 質問は自然文でよい。検索キーワードは Gemini が咀嚼して自動で組む。
- モデル既定 `gemini-3.5-flash`。変えるなら第2引数か環境変数 `GEMINI_MODEL`。
- 出力は stdout（回答 → Gemini が使った検索クエリ → ソースURL）。`tail` で切らず全文を扱う。
- 所要 ~15〜20秒（grounding のため）。

## 挙動
- Gemini API の `google_search` グラウンディングを**単発で1回**呼ぶ（ループしない）。
- ソースは grounding の redirect URL を実URLに解決して表示（best-effort）。

## いつ使うか
- **「Googleで調べて」等、ユーザーが明示的に Google 検索を求めたとき**に使う。
- 内蔵 WebSearch の自動全置換ではない。指示があったら本 skill で検索する。
- 用途: 最新情報・事実確認の web 検索、根拠付き回答、セカンドオピニオン。
