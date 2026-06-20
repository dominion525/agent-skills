---
name: goose
description: >
  Delegates a self-contained agentic task to Google Gemini via the Block Goose CLI,
  run headlessly from Claude Code. Goose can autonomously explore the repository,
  read files, and execute shell commands across multiple turns to produce a result
  rather than a single-shot answer. Use when offloading exploratory analysis to a
  different model family, getting a second opinion on a diff or design, or running
  a multi-step task that needs tool use beyond what a single prompt can return.
allowed-tools: Bash
---

# goose — Gemini に agentic タスクを委譲する

Block の Goose CLI を Google Gemini で headless 駆動し、Claude Code から別系統モデルに自己完結タスクを丸投げするための薄いラッパー。Goose 自身がファイルを読み、コマンドを実行しながら、複数ターンの自走で結果を返す。Codex (OpenAI) と並ぶ「もう一つの委譲先」として使う。

## 前提

- `goose` CLI 導入済み (`brew install block-goose-cli`)。
- `goose configure` で Google Gemini をプロバイダ設定済み。API キーは macOS Keychain に格納される（**このスキルはキーを保持しない**）。
- 動作中の provider / model を確認したいときは `~/.config/goose/config.yaml` の `active_provider` を見るか、`goose run` の起動バナーを読む。`goose info` は provider / model を出さないので使わない。

## 呼び出し

Goose に作業させたいディレクトリで実行する:

```bash
goose run --no-session --max-turns 20 -t "<自己完結したタスク>"
```

- `--no-session`: セッションファイルを作らない自動実行向け。
- `--max-turns N`: 自律ループの上限（暴走防止）。10〜25 が目安。
- provider / model は `goose configure` で設定済みのものをそのまま使うため、呼び出し時の指定は不要。
- 出力（思考・ツール呼び出し・最終回答）は stdout に出る。`tail` 等で切らずに全文を扱う。

別モデルで一度だけ上書きしたいときは `GOOSE_MODEL` を使う（指定モデルが当該プロバイダで利用可能であること）:

```bash
GOOSE_MODEL=<別のモデル名> goose run --no-session --max-turns 25 -t "<タスク>"
```

## 挙動と注意

- Goose は developer 拡張経由でファイル読み取りと shell 実行ができる自律エージェント。リポジトリを走査してレポートを返せる。
- 書き込みや破壊的 shell 実行も技術的には可能で、`--no-session` や上記の呼び出しオプションでは権限制限されない。読み取り目的のタスクは「分析・レビュー・レポート」と明示し、書き換えや破壊操作を依頼しない。
- 巨大なリポジトリでは探索に時間とトークンを消費するため、対象ファイル・ディレクトリを絞って依頼する。

## 向いている用途

- 「このリポジトリを調べてアーキテクチャを箇条書きで報告して」
- 「ファイル X / この差分を、別モデルの視点でレビューして」
- Codex や Claude の結論と突き合わせるセカンドオピニオン。
