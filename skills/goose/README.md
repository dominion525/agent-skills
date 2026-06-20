# goose

Claude Code から Google Gemini（Block の Goose CLI 経由）に agentic タスクを委譲するための薄い skill。

## 前提

- `goose` CLI 導入（`brew install block-goose-cli`）
- `goose configure` で Google Gemini を設定（API キーは macOS Keychain 保存・skill はキー非保持）

## 何をするか

`goose run --no-session --max-turns N -t "<タスク>"` を Gemini 頭脳で headless 実行し、
リポジトリ走査・レビュー・セカンドオピニオンなどを別モデル系統に委譲する。Codex と併用する想定。
詳細は `skills/goose/SKILL.md` を参照。
