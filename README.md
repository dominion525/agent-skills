[日本語](README.ja.md) | **English**

# agent-skills

A collection of Skills for Claude Code.

## Included Skills

- `skills/gsearch/` — Returns grounded Google search results via Gemini's `google_search`
- `skills/goose/` — Delegates self-contained agentic tasks to Gemini via the Goose CLI
- `skills/loki-activity/` — Aggregates Claude Code activity from Grafana Loki
- `skills/jetdb-cli/` — Read-only CLI for Microsoft Access (.mdb/.accdb) databases
- `skills/tgltrk/` — Operates Toggl Track time tracking from the CLI

See each `SKILL.md` for details.

## Installation

Via Claude Code Plugin Marketplace:

```
/plugin marketplace add dominion525/agent-skills
/plugin install gsearch@dominion525-skills   # gsearch / goose / loki-activity / jetdb-cli / tgltrk
```

Via Vercel skills CLI:

```
npx skills add dominion525/agent-skills --skill gsearch -a claude-code
```
