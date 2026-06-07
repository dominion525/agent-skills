---
name: goose
description: Delegate a self-contained, agentic task to Google Gemini via the Goose CLI, run headlessly from Claude Code. Goose autonomously explores the repo, reads files, runs read-only shell, and reports back — a different model family for second opinions, cross-model review, or offloading exploratory analysis. Use alongside Codex. Not for destructive/write tasks unless explicitly intended.
---

# goose — Gemini に agentic タスクを委譲する

Block の Goose エージェントを headless で起動し、頭脳を Google Gemini にして走らせる。Claude Code から「別系統のモデルに自己完結タスクを丸投げ」して、単発回答ではなく**ツールを使う自律的な結果**を受け取るための薄いラッパー。Codex(OpenAI) と併用する「2台目の委譲先」。

## 前提

- `goose` CLI 導入済み（`brew install block-goose-cli`）。
- `goose configure` でプロバイダ設定済み: Google Gemini / API キーは macOS Keychain / モデル `gemini-3.5-flash`。**このスキルはキーを保持しない**。
- 確認: `goose info` で provider が google。

## 呼び出し

Goose に作業させたいディレクトリで実行する:

```bash
goose run --no-session --max-turns 20 -t "<自己完結したタスク>"
```

- `--no-session`: セッションファイルを作らない自動実行向け。
- `--max-turns N`: 自律ループの上限（暴走防止）。10〜25 が目安。
- provider/model は goose config（Google Gemini / gemini-3.5-flash）を使うので、ここでは指定不要。
- 出力（思考・ツール呼び出し・最終回答）は stdout に出る。`tail` 等で切らずに全文を扱う。

別モデルを使いたい1回だけは `GOOSE_MODEL` で上書きできる（その時点でアカウントが使えるモデルに限る）:

```bash
GOOSE_MODEL=<別のgeminiモデル> goose run --no-session --max-turns 25 -t "<タスク>"
```

## 挙動と注意

- Goose は**本物のエージェント**: ファイルを読み、shell を実行できる（developer 拡張）。リポジトリを走査してレポートできる。
- 読み取り目的なら、タスク文を「分析・レビュー・レポート」と表現し、ファイル変更を頼まない。
- 書き込み/shell 権限を持って動くため、破壊的タスクを安易に委譲しない。
- 巨大 repo は時間・トークンを食う。対象を絞って依頼する。

## 向いている用途

- 「このリポジトリを調べてアーキテクチャを箇条書きで報告して」
- 「ファイル X / この差分を、別モデルの視点でレビューして」
- Codex や Claude の結論と突き合わせるセカンドオピニオン。
