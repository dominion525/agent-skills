# agent-skills

Claude Code 向けの Skill 集。

## 収録 Skill

- `gsearch-skill/` — gsearch: Gemini の google_search でグラウンディングされた Google 検索を返す
- `goose-skill/` — goose: Goose CLI 経由で Gemini に自走タスクを委譲する
- `blog-writing-skill/` — blog-writing: はてなブログの記事執筆を支援する
- `loki-logcli-skill/` — loki-activity: Grafana Loki から Claude Code の作業時間を集計する

各 Skill の詳細は配下の `README.md` および `skills/<name>/SKILL.md` を参照。

## インストール

各 Skill ディレクトリ配下の `skills/<name>/` を Claude Code のスキル置き場（例: `~/.claude/skills/<name>/`）に配置すると有効になる。
