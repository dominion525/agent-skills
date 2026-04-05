---
name: loki-activity
description: >
  Claude Codeの作業時間をGrafana Loki/logcliから取得して集計する。
  OTELテレメトリデータからプロジェクト別の作業ブロックと合計時間を算出する。
  「今日の作業時間」「今週の稼働」「プロジェクト別の作業サマリー」等を
  問い合わせたいときに使用する。
allowed-tools: Bash, Read
---

# loki-activity スキル

Grafana Lokiに蓄積されたClaude CodeのOTELテレメトリから、
プロジェクト別の作業時間を集計してレポートする。

## 前提条件

- `logcli` がインストール済み
- 環境変数 `LOKI_ADDR`, `LOKI_USERNAME`, `LOKI_PASSWORD` が設定済み
- `jq` がインストール済み

## 引数の処理

`$ARGUMENTS` を以下のルールで解析する:

| ユーザー入力 | 解釈 | スクリプト引数 |
|---|---|---|
| (なし) | 過去24時間、現在のプロジェクト | (デフォルト: カレントリポジトリ名で自動フィルタ) |
| `3` | 過去3日分、現在のプロジェクト | `--since 72h` |
| `all` | 過去24時間、全プロジェクト | `--all` |
| `all 3` | 過去3日分、全プロジェクト | `--all --since 72h` |
| `aleister` | 過去24h、特定プロジェクト | `--project aleister` |
| `aleister 7` | 過去7日、特定プロジェクト | `--project aleister --since 168h` |
| `week` | 過去7日、現在のプロジェクト | `--since 168h` |
| `month` | 過去30日、現在のプロジェクト | `--since 720h` |
| `all week` | 過去7日、全プロジェクト | `--all --since 168h` |

数値はN日分を意味し、N * 24 で時間に換算する。
`week` と `month` はそれぞれ 168h、720h のエイリアス。
文字列は `service_namespace` の部分一致フィルタとして扱う。
`all` を指定すると全プロジェクトを対象にする。
デフォルトではカレントリポジトリ名（`git rev-parse --show-toplevel` のbasename）で自動フィルタする。

## スクリプト呼び出し

解析した引数をもとに、以下のようにスクリプトを呼び出す:

```bash
bash ~/.claude/skills/loki-activity/scripts/activity.sh [OPTIONS]
```

オプション:
- `--since DURATION` — 期間（logcli形式: `24h`, `168h`, `720h`）
- `--project NAME` — プロジェクトフィルタ（service_namespace部分一致）
- `--all` — 全プロジェクトを対象にする（デフォルトのカレントリポジトリ自動フィルタを無効化）
- `--detail` — 全イベント一覧を出力する（デフォルトはサマリー）
- `--interval N` — サマリーの区切り分数（デフォルト: 10）

`--project` も `--all` も指定しない場合、カレントリポジトリ名で自動的にフィルタされる。

## スクリプトの出力

### サマリーモード（デフォルト）

時間帯ごとにイベント数を集計した要約を返す。

```json
{
  "query_params": { "since": "24h", "project_filter": "sandbox", "mode": "summary", "interval_minutes": 10 },
  "projects": [
    {
      "namespace": "sandbox",
      "interval_minutes": 10,
      "slots": [
        { "time_utc": "2026-04-05T04:30:00Z", "total": 35, "user_prompt": 3, "api_request": 11, "tool_use": 21 },
        { "time_utc": "2026-04-05T04:40:00Z", "total": 23, "user_prompt": 2, "api_request": 6, "tool_use": 15 }
      ]
    }
  ]
}
```

各スロットのフィールド:
- `time_utc` — 時間帯の開始時刻（UTC）
- `total` — その時間帯のイベント総数
- `user_prompt` — 人間がプロンプトを送信した回数（人間のアクティビティの確実な証拠）
- `api_request` — Claude APIリクエスト数（Claudeが処理中。数分から10分かかることもある）
- `tool_use` — ツール実行関連のイベント数（tool_result + tool_decision）

### ディテールモード（--detail）

全イベントの一覧を時系列で返す。データ量が多くなるため、特定の時間帯を詳しく調べたい場合に使う。

## 作業ブロックの判定（あなたが行う）

サマリーのスロット一覧を見て、「人間が作業していたと思われるひとかたまりの時間帯」を判断する。
機械的な固定閾値で切るのではなく、文脈を読んで判断すること。

判断の目安:
- `user_prompt` が含まれるスロットは人間が能動的に操作していた証拠
- `user_prompt` がなくても `api_request` や `tool_use` が多いスロットは、Claudeが処理中（数分から10分かかることもある）
- スロットが連続していれば一連の作業とみなす
- 空のスロット（データなし）が挟まっていても、前後の文脈から一連の作業と判断できるならまとめてよい
- 完璧でなくてよい。後で人間が補正する前提

## レポートのフォーマット

タイムスタンプはUTCからJST（+9時間）に変換して表示する。

プロジェクトごとに作業ブロックの開始・終了時刻と推定時間を出す。
複数プロジェクトがある場合はプロジェクト別にまとめる。

データが0件の場合は「該当期間にイベントが見つかりませんでした」と報告する。

## ヒートマップ表示

ユーザーが「ヒートマップ」「heatmap」「可視化」等と言った場合、activity.shの出力をヒートマップスクリプトにパイプして表示する。

```bash
bash ~/.claude/skills/loki-activity/scripts/activity.sh [OPTIONS] | uv run ~/.claude/skills/loki-activity/scripts/heatmap.py [--color]
```

- デフォルトはASCIIモード（ブロック文字で密度表示）
- `--color` をつけるとTrueColorモード（GitHubの草風の緑グラデーション）
- `--metric` で表示メトリクスを変更可能（total, user_prompt, api_request, tool_use）
- activity.shのオプション（`--all`, `--since`, `--project`）はそのまま使える
