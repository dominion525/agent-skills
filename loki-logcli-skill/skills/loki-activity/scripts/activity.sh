#!/usr/bin/env bash
set -euo pipefail

# ===== 依存コマンドチェック =====
for cmd in logcli jq git; do
  if ! command -v "$cmd" > /dev/null 2>&1; then
    echo "エラー: $cmd が見つかりません。インストールしてください。" >&2
    exit 1
  fi
done

# ===== デフォルト値 =====
SINCE="24h"
PROJECT=""
ALL=false
MODE="summary"
INTERVAL=10  # サマリーの区切り（分）

# ---------------------------------------------------------------------------
# 関数定義
# ---------------------------------------------------------------------------

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --since)
        [[ $# -ge 2 && ! "$2" =~ ^-- ]] || { echo "エラー: --since には値が必要です" >&2; exit 1; }
        SINCE="$2"; shift 2 ;;
      --project)
        [[ $# -ge 2 && ! "$2" =~ ^-- ]] || { echo "エラー: --project には値が必要です" >&2; exit 1; }
        PROJECT="$2"; shift 2 ;;
      --all)      ALL=true;      shift ;;
      --detail)   MODE="detail"; shift ;;
      --interval)
        [[ $# -ge 2 && ! "$2" =~ ^-- ]] || { echo "エラー: --interval には値が必要です" >&2; exit 1; }
        INTERVAL="$2"; shift 2 ;;
      *)          echo "エラー: 不明なオプション: $1" >&2; exit 1 ;;
    esac
  done

  # INTERVALのバリデーション
  if ! [[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
    echo "エラー: --interval は正の整数を指定してください: $INTERVAL" >&2
    exit 1
  fi
}

resolve_project() {
  if [[ -z "$PROJECT" && "$ALL" == false ]]; then
    PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null) || true
  fi
}

build_query() {
  local project="$1"
  if [[ -n "$project" ]]; then
    echo "{service_name=\"claude-code\", service_namespace=~\".*${project}.*\"}"
  else
    echo '{service_name="claude-code"}'
  fi
}

fetch_events() {
  local query="$1"
  local since="$2"
  local raw exit_code=0

  raw=$(logcli query "$query" \
    --since="$since" \
    --limit=0 \
    --quiet \
    --include-label=service_namespace \
    --include-label=event_name \
    --include-label=event_timestamp \
    --output=jsonl 2>&1) || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    echo "エラー: logcli の実行に失敗しました (exit code: $exit_code)" >&2
    echo "$raw" >&2
    return 1
  fi

  echo "$raw"
}

empty_response() {
  local since="$1"
  local project="$2"
  local mode="$3"
  jq -n \
    --arg since "$since" \
    --arg project "$project" \
    --arg mode "$mode" \
    '{query_params: {since: $since, project_filter: $project, mode: $mode}, projects: []}'
}

format_detail() {
  local since="$1"
  local project="$2"
  jq -s \
    --arg since "$since" \
    --arg project "$project" \
  '
  [.[] | {
    namespace: (if (.labels.service_namespace // "") == "" then "(unset)" else .labels.service_namespace end),
    timestamp: .labels.event_timestamp,
    event: .labels.event_name
  }]
  | sort_by(.timestamp)
  | group_by(.namespace)
  | map({
      namespace: .[0].namespace,
      events: [.[] | {timestamp: .timestamp, event: .event}]
    })
  | {
      query_params: {
        since: $since,
        project_filter: $project,
        mode: "detail"
      },
      projects: .
    }
  '
}

format_summary() {
  local since="$1"
  local project="$2"
  local interval="$3"
  jq -s \
    --arg since "$since" \
    --arg project "$project" \
    --argjson interval "$interval" \
  '
  def to_epoch:
    sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601;

  # 区切り秒数
  ($interval * 60) as $bucket_sec |

  [.[] | {
    namespace: (if (.labels.service_namespace // "") == "" then "(unset)" else .labels.service_namespace end),
    timestamp: .labels.event_timestamp,
    event: .labels.event_name
  }]
  | sort_by(.timestamp)
  | group_by(.namespace)
  | map(
      .[0].namespace as $ns |
      # 各イベントにバケットキーを付与
      [.[] | {
        event: .event,
        ts: .timestamp,
        epoch: (.timestamp | to_epoch),
        bucket: ((.timestamp | to_epoch) / $bucket_sec | floor * $bucket_sec)
      }]
      | group_by(.bucket)
      | map(
          .[0].bucket as $b |
          {
            time_utc: ($b | strftime("%Y-%m-%dT%H:%M:%SZ")),
            total: length,
            user_prompt: [.[] | select(.event == "user_prompt")] | length,
            api_request: [.[] | select(.event == "api_request")] | length,
            tool_use: [.[] | select(.event == "tool_result" or .event == "tool_decision")] | length
          }
        )
      | {
          namespace: $ns,
          interval_minutes: $interval,
          slots: .
        }
    )
  | {
      query_params: {
        since: $since,
        project_filter: $project,
        mode: "summary",
        interval_minutes: $interval
      },
      projects: .
    }
  '
}

main() {
  parse_args "$@"
  resolve_project

  local query
  query=$(build_query "$PROJECT")

  local raw
  if ! raw=$(fetch_events "$query" "$SINCE"); then
    exit 1
  fi

  if [[ -z "$raw" ]]; then
    empty_response "$SINCE" "$PROJECT" "$MODE"
  elif [[ "$MODE" == "detail" ]]; then
    echo "$raw" | format_detail "$SINCE" "$PROJECT"
  else
    echo "$raw" | format_summary "$SINCE" "$PROJECT" "$INTERVAL"
  fi
}

# ---------------------------------------------------------------------------
# エントリポイント（sourceされた場合は実行しない）
# ---------------------------------------------------------------------------

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
