---
name: tgltrk
description: >
  Toggl Track の時間計測を CLI から操作する。タイマーの開始 / 停止、
  時間エントリの一覧 / 作成 / 編集 / 削除、プロジェクト・クライアント・
  タグの管理を行う。Toggl Track、時間計測、タイマー、作業ログに関する
  指示を受けたときに使用する。
allowed-tools: Bash
---

# tgltrk CLI

Toggl Track 向けの読み書き対応 CLI。単一 Rust バイナリ、ランタイム依存なし。

```
cargo install tgltrk
```

## 運用ルール

```
tgltrk [--json] [--workspace <ID>] <COMMAND> [OPTIONS]
```

- **認証**: 初回は `tgltrk auth login`（対話的にトークン入力）または環境変数 `TOGGL_API_TOKEN` を設定。env var が保存済みトークンより優先される。
- **プロジェクト / クライアント / タグの識別子は数値 ID**。`-p / --project` は **PROJECT_ID（数値）専用、プロジェクト名は渡せない**。名前から ID を解決する場合は先に `tgltrk projects list` を実行する。
- **時刻入力**（`--start`、`--stop`）は RFC 3339 UTC（例 `2026-06-21T09:00:00Z`）またはローカル時刻（`YYYY-MM-DD[T]HH:MM[:SS]`）を受け付ける。ローカル時刻は実行ホストのタイムゾーンで解釈され、DST 曖昧時刻ではエラーになる。
- **継続時間**（`--duration`）は `h/m/s` 形式（`1h30m`、`90m`、`45s`）または秒数の整数（`5400`）を受け付ける。正の値であること。
- **ワークスペース**: `--workspace <ID>` は project / client / tag の変更系、および `timer start` / `entries create` のデフォルト workspace を上書きする。`entries edit` / `entries delete` では、指定があれば上書きし、なければ対象エントリ自身の workspace を使う。`entries list`、`timer current`、`entries continue`（常に元エントリの workspace を使用）、`cache` では無視される。
- **終了コード**: 成功 → 0、実行時エラー（認証なし、API エラー、不正な日付等）→ 1 で stderr に `Error: ...`、CLI 引数エラー（未知のフラグ、必須値なし等）→ 2 で stderr に `error: ...`。
- **list 系コマンド**でデータがない場合 → exit 0、空 stdout。
- **`--json`** は `{meta, data}` エンベロープを出力する。単純な確認用途ではプレーンテキストの方がトークン効率がよい。

## クイックリファレンス

| 目的                  | コマンド                                                               |
|-----------------------|------------------------------------------------------------------------|
| 実行中タイマー確認    | `tgltrk timer current`                                                 |
| タイマー開始          | `tgltrk timer start -d "desc" -p PROJECT_ID`                           |
| タイマー停止          | `tgltrk timer stop`                                                    |
| エントリ一覧          | `tgltrk entries list -n 10`                                            |
| 日付範囲で絞り込み    | `tgltrk entries list --since YYYY-MM-DD --until YYYY-MM-DD`            |
| 過去エントリを作成    | `tgltrk entries create --start <ISO8601> --stop <ISO8601> -d "desc"`   |
| 継続時間で作成        | `tgltrk entries create --start <ISO8601> --duration "1h30m" -d "desc"` |
| エントリを継続        | `tgltrk entries continue ENTRY_ID`                                     |
| エントリを編集        | `tgltrk entries edit ENTRY_ID -d "new desc"`                           |
| エントリの時刻を編集  | `tgltrk entries edit ENTRY_ID --start <ISO8601> --stop <ISO8601>`      |
| エントリを削除        | `tgltrk entries delete ENTRY_ID`                                       |
| プロジェクト一覧      | `tgltrk projects list`（クライアント名を [] 内に表示）                 |
| プロジェクト作成      | `tgltrk projects create "name" [--client CLIENT_ID]`                   |
| プロジェクト更新      | `tgltrk projects update ID [--name "..."] [--client CLIENT_ID]`        |
| クライアント一覧      | `tgltrk clients list`                                                  |
| クライアント取得      | `tgltrk clients get CLIENT_ID`                                         |
| クライアント作成      | `tgltrk clients create "name"`                                         |
| クライアント更新      | `tgltrk clients update CLIENT_ID --name "new name"`                    |
| クライアント削除      | `tgltrk clients delete CLIENT_ID`                                      |
| タグ一覧              | `tgltrk tags list`                                                     |
| タグ作成              | `tgltrk tags create "name"`                                            |
| ワークスペース一覧    | `tgltrk workspaces list`                                               |
| ワークスペース取得    | `tgltrk workspaces get WORKSPACE_ID`                                   |
| キャッシュ状態        | `tgltrk cache status`                                                  |
| キャッシュクリア      | `tgltrk cache clear`                                                   |

各コマンドの詳細オプションは `tgltrk <command> --help` を参照。各コマンドのセマンティクスとエッジケースは下記の詳細セクションを参照。

## コマンド

### timer — 実行中タイマー

```
tgltrk timer start                                       # 空タイマーを開始（説明・プロジェクトなし）
tgltrk timer start -d "description"                      # 説明のみ
tgltrk timer start -d "description" -p PROJECT_ID -t tag1,tag2
tgltrk timer stop                                        # 実行中タイマーを停止
tgltrk timer current                                     # 実行中タイマーを表示
```

- `timer start` は引数なしで実行可能 — Toggl は未割当のタイマーを開始する。後から `entries edit` で項目を埋められる。
- `-b / --billable` はこのコマンドでは値なしの真偽フラグ（指定あり = true）。
- `timer stop` を実行中タイマーがない状態で呼ぶ → 実行時エラー（exit 1）。
- `timer current` を実行中タイマーがない状態で呼ぶ → exit 0、`No running timer` を出力（`--json` 指定時は `data: null`）。エラー扱いではない。

### entries — 時間エントリ

```
tgltrk entries list -n 10                                                                    # 直近 N 件
tgltrk entries list --since YYYY-MM-DD --until YYYY-MM-DD                                    # 日付範囲
tgltrk entries continue ENTRY_ID                                                             # エントリを複製して新タイマー開始
tgltrk entries create --start <ISO8601> --stop <ISO8601> -d "description" -p PROJECT_ID      # 過去エントリ
tgltrk entries create --start <ISO8601> --duration "1h30m" -d "description"                  # 継続時間指定
tgltrk entries edit ENTRY_ID [-d "..."] [-p PROJECT_ID] [-t tag1,tag2] [-b true|false] [--start ...] [--stop ...] [--duration ...]
tgltrk entries delete ENTRY_ID
```

- `-n` は `--count <N>` の短縮形。
- `entries create` は `--start` と **`--stop` または `--duration` のいずれか一方**が必須。両方指定、`--stop ≤ --start`、非正の継続時間はエラー。
- `entries edit`: `--stop` と `--duration` は排他。**`-b / --billable` はこのコマンドでは `true` / `false` の引数が必須**（`timer start` / `entries create` の値なし真偽フラグとは異なる）。指定したフィールドのみ更新される。
- `entries continue` は description / project / tags / task / billable を複製し、**元エントリの workspace で開始する**。`--workspace` で上書きできない。

### projects — プロジェクト

```
tgltrk projects list                                       # クライアント名を [] 内に表示
tgltrk projects create "name" [--client CLIENT_ID]
tgltrk projects update ID [--name "..."] [--client CLIENT_ID]
```

### clients — クライアント

```
tgltrk clients list
tgltrk clients get CLIENT_ID
tgltrk clients create "name"
tgltrk clients update CLIENT_ID --name "new name"
tgltrk clients delete CLIENT_ID
```

### tags — タグ

```
tgltrk tags list
tgltrk tags create "name"
```

### workspaces — ワークスペース（読み取り専用）

```
tgltrk workspaces list
tgltrk workspaces get WORKSPACE_ID
```

この CLI でワークスペースの作成・編集はできない。`--workspace` はコマンドの対象 workspace を選択するだけ。

### cache — ローカルキャッシュ

```
tgltrk cache status                                        # キャッシュディレクトリ、キー、サイズ、更新時刻を表示
tgltrk cache clear
```

`cache` コマンドは認証不要。

## JSON 出力

```json
{
  "meta": { "cached": ["projects"] },
  "data": { ... }
}
```

- `meta.cached` はこの呼び出しでローカルキャッシュから返した entity 一覧。**空配列の場合はキャッシュヒットなし**（API から取得）を意味する。逆ではない。
- `data` はコマンド結果。削除操作では `null`、`timer current` でタイマーが実行中でない場合も `null`。

## キャッシュ動作

- ユーザー情報、プロジェクト、クライアント、タグ、ワークスペースは **72 時間**ローカルキャッシュされる（API 呼び出し削減と Toggl のレート制限対策）。
- 該当 entity の create / update / delete で自動的に無効化される。
- **`auth login` 成功時に毎回全クリア**（アカウント切替時に限らない）。
- 手動クリア: `tgltrk cache clear`。

## 制約

- ワークスペースはこの CLI では読み取り専用（`--workspace` は選択のみ）。
- レポート系エンドポイント（Summary、Detailed、Weekly）は未対応。
- バルク操作（バッチ削除など）は未対応。
