#!/usr/bin/env bash
set -euo pipefail

# ===== デフォルト値 =====
SINCE="24h"
PROJECT=""
GAP_THRESHOLD=900

# ===== 引数パース =====
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)   SINCE="$2";         shift 2 ;;
    --project) PROJECT="$2";       shift 2 ;;
    --gap)     GAP_THRESHOLD="$2"; shift 2 ;;
    *)         echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ===== logcliクエリ構築 =====
if [[ -n "$PROJECT" ]]; then
  QUERY="{service_name=\"claude-code\", service_namespace=~\".*${PROJECT}.*\"}"
else
  QUERY='{service_name="claude-code"}'
fi

# ===== logcli実行 =====
RAW=$(logcli query "$QUERY" \
  --since="$SINCE" \
  --limit=0 \
  --quiet \
  --include-label=service_namespace \
  --include-label=event_name \
  --include-label=event_timestamp \
  --output=jsonl 2>/dev/null) || true

# イベント0件チェック
if [[ -z "$RAW" ]]; then
  jq -n \
    --arg since "$SINCE" \
    --arg project "$PROJECT" \
    --argjson gap "$GAP_THRESHOLD" \
    '{
      query_params: {since: $since, project_filter: $project, gap_threshold_sec: $gap},
      projects: [],
      grand_total_sec: 0,
      grand_total_human: "0m"
    }'
  exit 0
fi

# ===== jqで作業ブロック集計 =====
echo "$RAW" | jq -s \
  --argjson gap "$GAP_THRESHOLD" \
  --arg since "$SINCE" \
  --arg project "$PROJECT" \
'
# 秒を人間可読に変換
def human_duration:
  if . >= 3600 then
    "\(. / 3600 | floor)h \((. % 3600) / 60 | floor)m"
  elif . >= 60 then
    "\(. / 60 | floor)m"
  else
    "\(.)s"
  end;

# ISO8601からミリ秒を除去してエポック秒に変換
def to_epoch:
  sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601;

# 1. イベントを構造化
[.[] | {
  ns: (if (.labels.service_namespace // "") == "" then "(unset)" else .labels.service_namespace end),
  ts: .labels.event_timestamp,
  ev: .labels.event_name
}]
| sort_by(.ts)

# 2. namespace別にグループ化
| group_by(.ns)
| map(
    sort_by(.ts) as $sorted
    | ($sorted | first | .ns) as $ns

    # 3. 作業ブロック検出
    | $sorted
    | reduce .[] as $e (
        {blocks: [], cs: null, ce: null};
        if .cs == null then
          .cs = $e.ts | .ce = $e.ts
        else
          (($e.ts | to_epoch) - (.ce | to_epoch)) as $diff
          | if $diff > $gap then
              .blocks += [{
                start: .cs,
                end: .ce,
                duration_sec: ((.ce | to_epoch) - (.cs | to_epoch))
              }]
              | .cs = $e.ts | .ce = $e.ts
            else
              .ce = $e.ts
            end
        end
      )
    # 最後のブロックを追加
    | .blocks += [{
        start: .cs,
        end: .ce,
        duration_sec: ((.ce | to_epoch) - (.cs | to_epoch))
      }]
    | .blocks |= map(. + {duration_human: (.duration_sec | human_duration)})
    | {
        namespace: $ns,
        blocks: .blocks,
        total_sec: ([.blocks[].duration_sec] | add // 0),
        total_human: (([.blocks[].duration_sec] | add // 0) | human_duration),
        block_count: (.blocks | length)
      }
  )
| sort_by(-.total_sec)

# 4. 全体サマリー
| {
    query_params: {
      since: $since,
      project_filter: $project,
      gap_threshold_sec: $gap,
      generated_at: (now | strftime("%Y-%m-%dT%H:%M:%S+09:00"))
    },
    projects: .,
    grand_total_sec: ([.[].total_sec] | add // 0),
    grand_total_human: (([.[].total_sec] | add // 0) | human_duration)
  }
'
