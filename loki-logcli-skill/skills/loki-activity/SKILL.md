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
| (なし) | 過去24時間、全プロジェクト | (デフォルト) |
| `3` | 過去3日分 | `--since 72h` |
| `aleister` | 過去24h、特定プロジェクト | `--project aleister` |
| `aleister 7` | 過去7日、特定プロジェクト | `--project aleister --since 168h` |
| `week` | 過去7日 | `--since 168h` |
| `month` | 過去30日 | `--since 720h` |

数値はN日分を意味し、N * 24 で時間に換算する。
`week` と `month` はそれぞれ 168h、720h のエイリアス。
文字列は `service_namespace` の部分一致フィルタとして扱う。

## スクリプト呼び出し

解析した引数をもとに、以下のようにスクリプトを呼び出す:

```bash
bash ~/.claude/skills/loki-activity/scripts/activity.sh [OPTIONS]
```

オプション:
- `--since DURATION` — 期間（logcli形式: `24h`, `168h`, `720h`）
- `--project NAME` — プロジェクトフィルタ（service_namespace部分一致）
- `--gap SECONDS` — 作業ブロック分割閾値（デフォルト: 900秒 = 15分）

## 出力の解釈

スクリプトはJSON形式で結果を返す。以下の構造に従って人間が読みやすい日本語レポートに整形すること。

### JSONの構造

```json
{
  "query_params": { "since": "24h", "gap_threshold_sec": 900 },
  "projects": [
    {
      "namespace": "プロジェクト名",
      "blocks": [
        { "start": "ISO8601(UTC)", "end": "ISO8601(UTC)", "duration_sec": 数値, "duration_human": "2h 12m" }
      ],
      "total_sec": 数値,
      "total_human": "2h 12m",
      "block_count": 数値
    }
  ],
  "grand_total_sec": 数値,
  "grand_total_human": "4h 02m"
}
```

### レポートのフォーマット

以下の形式で出力すること:

1. **ヘッダー**: 期間とフィルタ条件
2. **プロジェクト別サマリー**: テーブル形式（プロジェクト名、合計時間、ブロック数）
3. **タイムライン詳細**: プロジェクトごとに作業ブロックの開始・終了時刻をJSTで表示
4. **合計**: 全プロジェクト合計の作業時間

タイムスタンプはUTCからJST（+9時間）に変換して表示する。

### 注意事項

- 作業時間は推定値。ブロック判定は15分のギャップ閾値に基づく
- 並行作業（複数プロジェクト同時稼働）の場合、合計は二重カウントになる。その旨を注記すること
- `namespace` が `(unset)` のプロジェクトは「(未設定)」として表示する
- データが0件の場合は「該当期間にイベントが見つかりませんでした」と報告する
