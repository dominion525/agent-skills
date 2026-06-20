**日本語** | [English](README.md)

# agent-skills

Claude Code 向けの Skill 集。

## 収録 Skill

- `skills/gsearch/` — Gemini の google_search でグラウンディングされた Google 検索を返す
- `skills/goose/` — Goose CLI 経由で Gemini に自走タスクを委譲する
- `skills/loki-activity/` — Grafana Loki から Claude Code の作業時間を集計する
- `skills/jetdb-cli/` — Microsoft Access (.mdb/.accdb) データベースの読み取り専用 CLI
- `skills/tgltrk/` — Toggl Track の時間計測を CLI から操作する

各 Skill の詳細は配下の `SKILL.md` を参照。

## インストール

Claude Code Plugin Marketplace 経由:

```
/plugin marketplace add dominion525/agent-skills
/plugin install gsearch@dominion525-skills   # gsearch / goose / loki-activity / jetdb-cli / tgltrk
```

Vercel skills CLI 経由:

```
npx skills add dominion525/agent-skills --skill gsearch -a claude-code
```
