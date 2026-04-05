#!/usr/bin/env bash
set -euo pipefail

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
      --since)    SINCE="$2";    shift 2 ;;
      --project)  PROJECT="$2";  shift 2 ;;
      --all)      ALL=true;      shift ;;
      --detail)   MODE="detail"; shift ;;
      --interval) INTERVAL="$2"; shift 2 ;;
      *)          echo "Unknown option: $1" >&2; exit 1 ;;
    esac
  done
}

resolve_project() {
  if [[ -z "$PROJECT" && "$ALL" == false ]]; then
    PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null) || true
  fi
}

build_query() {
  if [[ -n "$PROJECT" ]]; then
    echo "{service_name=\"claude-code\", service_namespace=~\".*${PROJECT}.*\"}"
  else
    echo '{service_name="claude-code"}'
  fi
}

fetch_events() {
  local query="$1"
  logcli query "$query" \
    --since="$SINCE" \
    --limit=0 \
    --quiet \
    --include-label=service_namespace \
    --include-label=event_name \
    --include-label=event_timestamp \
    --output=jsonl 2>/dev/null || true
}

empty_response() {
  echo '{"query_params":{"since":"'"$SINCE"'","project_filter":"'"$PROJECT"'","mode":"'"$MODE"'"},"projects":[]}'
}

format_detail() {
  jq -s \
    --arg since "$SINCE" \
    --arg project "$PROJECT" \
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
  jq -s \
    --arg since "$SINCE" \
    --arg project "$PROJECT" \
    --argjson interval "$INTERVAL" \
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
  query=$(build_query)

  local raw
  raw=$(fetch_events "$query")

  if [[ -z "$raw" ]]; then
    empty_response
  elif [[ "$MODE" == "detail" ]]; then
    echo "$raw" | format_detail
  else
    echo "$raw" | format_summary
  fi
}

# ---------------------------------------------------------------------------
# エントリポイント（sourceされた場合は実行しない）
# ---------------------------------------------------------------------------

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
