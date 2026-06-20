---
name: tgltrk
description: >
  Operates Toggl Track time tracking from the CLI. Starts and stops timers,
  lists / creates / edits / deletes time entries, and manages projects,
  clients, and tags. Use when the user mentions Toggl Track, time tracking,
  timers, or work logging.
allowed-tools: Bash
---

# tgltrk CLI

Read / write CLI for Toggl Track. Single Rust binary, no runtime dependencies.

```
cargo install tgltrk
```

## Operating Rules

```
tgltrk [--json] [--workspace <ID>] <COMMAND> [OPTIONS]
```

- **Authentication**: run `tgltrk auth login` once (interactive token entry), or set the env var `TOGGL_API_TOKEN`. The env var takes precedence over the stored token.
- **Project / client / tag identifiers** are numeric IDs. `-p / --project` takes a **PROJECT_ID, not a project name** — resolve names with `tgltrk projects list` first.
- **Time inputs** (`--start`, `--stop`) accept RFC 3339 UTC (e.g. `2026-06-21T09:00:00Z`) or local time (`YYYY-MM-DD[T]HH:MM[:SS]`). Local values are interpreted in the host timezone and fail on DST-ambiguous moments.
- **Duration** (`--duration`) accepts `h/m/s` form (`1h30m`, `90m`, `45s`) or a plain seconds integer (`5400`). Must be positive.
- **Workspace**: `--workspace <ID>` overrides the default workspace for project / client / tag mutations and for `timer start` / `entries create`. For `entries edit` / `entries delete`, it overrides when provided and falls back to the target entry's own workspace otherwise. It is ignored by `entries list`, `timer current`, `entries continue` (always uses the original entry's workspace), and `cache`.
- **Exit codes**: success → 0; runtime errors (missing auth, API error, invalid date) → 1 with stderr `Error: ...`; CLI argument errors (unknown flag, missing required value) → 2 with stderr `error: ...`.
- **List-style commands** with no data print empty stdout and exit 0.
- **`--json`** emits an `{meta, data}` envelope; plain text is more token-efficient for simple checks.

## Quick Reference

| Purpose              | Command                                                                |
|----------------------|------------------------------------------------------------------------|
| Check current timer  | `tgltrk timer current`                                                 |
| Start timer          | `tgltrk timer start -d "desc" -p PROJECT_ID`                           |
| Stop timer           | `tgltrk timer stop`                                                    |
| List entries         | `tgltrk entries list -n 10`                                            |
| Filter by date       | `tgltrk entries list --since YYYY-MM-DD --until YYYY-MM-DD`            |
| Create past entry    | `tgltrk entries create --start <ISO8601> --stop <ISO8601> -d "desc"`   |
| Create with duration | `tgltrk entries create --start <ISO8601> --duration "1h30m" -d "desc"` |
| Continue entry       | `tgltrk entries continue ENTRY_ID`                                     |
| Edit entry           | `tgltrk entries edit ENTRY_ID -d "new desc"`                           |
| Edit entry time      | `tgltrk entries edit ENTRY_ID --start <ISO8601> --stop <ISO8601>`      |
| Delete entry         | `tgltrk entries delete ENTRY_ID`                                       |
| List projects        | `tgltrk projects list`  (shows client name in brackets)                |
| Create project       | `tgltrk projects create "name" [--client CLIENT_ID]`                   |
| Update project       | `tgltrk projects update ID [--name "..."] [--client CLIENT_ID]`        |
| List clients         | `tgltrk clients list`                                                  |
| Get client           | `tgltrk clients get CLIENT_ID`                                         |
| Create client        | `tgltrk clients create "name"`                                         |
| Update client        | `tgltrk clients update CLIENT_ID --name "new name"`                    |
| Delete client        | `tgltrk clients delete CLIENT_ID`                                      |
| List tags            | `tgltrk tags list`                                                     |
| Create tag           | `tgltrk tags create "name"`                                            |
| List workspaces      | `tgltrk workspaces list`                                               |
| Get workspace        | `tgltrk workspaces get WORKSPACE_ID`                                   |
| Cache status         | `tgltrk cache status`                                                  |
| Clear cache          | `tgltrk cache clear`                                                   |

Full options for each command are available via `tgltrk <command> --help`. Detailed semantics and edge cases are described per-command below.

## Commands

### timer — Running timer

```
tgltrk timer start                                       # Start an empty timer (no description / project)
tgltrk timer start -d "description"                      # With description only
tgltrk timer start -d "description" -p PROJECT_ID -t tag1,tag2
tgltrk timer stop                                        # Stops the running timer
tgltrk timer current                                     # Shows the running timer
```

- `timer start` accepts no arguments — Toggl creates an unassigned running timer; fill in fields later with `entries edit`.
- `-b / --billable` is a value-less boolean flag here (presence = true).
- `timer stop` with no running timer → runtime error (exit 1).
- `timer current` with no running timer → exit 0, prints `No running timer` (or `data: null` with `--json`); not an error.

### entries — Time entries

```
tgltrk entries list -n 10                                                                    # Recent N entries
tgltrk entries list --since YYYY-MM-DD --until YYYY-MM-DD                                    # Date range
tgltrk entries continue ENTRY_ID                                                             # Start a new timer cloning the entry
tgltrk entries create --start <ISO8601> --stop <ISO8601> -d "description" -p PROJECT_ID      # Past entry
tgltrk entries create --start <ISO8601> --duration "1h30m" -d "description"                  # By duration
tgltrk entries edit ENTRY_ID [-d "..."] [-p PROJECT_ID] [-t tag1,tag2] [-b true|false] [--start ...] [--stop ...] [--duration ...]
tgltrk entries delete ENTRY_ID
```

- `-n` is short for `--count <N>`.
- `entries create` requires `--start` plus **exactly one** of `--stop` or `--duration`. Specifying both, `--stop ≤ --start`, or a non-positive duration is an error.
- `entries edit`: `--stop` and `--duration` are mutually exclusive. **`-b / --billable` requires `true` or `false` here** (different from `timer start` / `entries create` where it is a value-less flag). Only specified fields are updated.
- `entries continue` clones description, project, tags, task, and billable, and starts in the original entry's workspace; `--workspace` does not override this.

### projects — Projects

```
tgltrk projects list                                       # Shows client name in brackets
tgltrk projects create "name" [--client CLIENT_ID]
tgltrk projects update ID [--name "..."] [--client CLIENT_ID]
```

### clients — Clients

```
tgltrk clients list
tgltrk clients get CLIENT_ID
tgltrk clients create "name"
tgltrk clients update CLIENT_ID --name "new name"
tgltrk clients delete CLIENT_ID
```

### tags — Tags

```
tgltrk tags list
tgltrk tags create "name"
```

### workspaces — Workspaces (read-only)

```
tgltrk workspaces list
tgltrk workspaces get WORKSPACE_ID
```

This CLI cannot create or modify workspaces; `--workspace` only selects which workspace a command targets.

### cache — Local cache

```
tgltrk cache status                                        # Show cache directory, keys, sizes, modification times
tgltrk cache clear
```

`cache` commands do not require authentication.

## JSON Output

```json
{
  "meta": { "cached": ["projects"] },
  "data": { ... }
}
```

- `meta.cached` lists entities returned from the local cache for this call. **An empty array means no cache hit** (data was fetched from the API), not that everything was cached.
- `data` is the command result. It is `null` for delete operations, and also for `timer current` when no timer is running.

## Cache Behavior

- User info, projects, clients, tags, and workspaces are cached locally for 72 hours to reduce API calls and stay within Toggl rate limits.
- Automatically invalidated on relevant entity create / update / delete.
- Cleared entirely on every successful `auth login` (not only on account switch).
- Manual clear: `tgltrk cache clear`.

## Limitations

- Workspaces are read-only via this CLI (`--workspace` only selects).
- Reporting endpoints (Summary, Detailed, Weekly) are not supported.
- Bulk operations (e.g. batch delete) are not supported.
