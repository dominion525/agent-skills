#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# activity.shの関数を読み込む（mainは実行されない）
source "$SCRIPT_DIR/activity.sh"

PASS=0
FAIL=0

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if diff <(echo "$actual") <(echo "$expected") > /dev/null 2>&1; then
    ((PASS++))
    echo "  PASS: $label"
  else
    ((FAIL++))
    echo "  FAIL: $label"
    diff <(echo "$actual") <(echo "$expected") || true
  fi
}

# ---------------------------------------------------------------------------
echo "=== build_query ==="
# ---------------------------------------------------------------------------

PROJECT=""
actual=$(build_query)
assert_eq "$actual" '{service_name="claude-code"}' "全件クエリ（PROJECT空）"

PROJECT="sandbox"
actual=$(build_query)
assert_eq "$actual" '{service_name="claude-code", service_namespace=~".*sandbox.*"}' "フィルタクエリ（PROJECT=sandbox）"

PROJECT="alpha-project"
actual=$(build_query)
assert_eq "$actual" '{service_name="claude-code", service_namespace=~".*alpha-project.*"}' "フィルタクエリ（ハイフン含む）"

# ---------------------------------------------------------------------------
echo "=== format_summary ==="
# ---------------------------------------------------------------------------

PROJECT=""
SINCE="24h"
INTERVAL=10

actual=$(cat "$SCRIPT_DIR/fixtures/sample.jsonl" | format_summary)
expected=$(cat "$SCRIPT_DIR/fixtures/expected_summary.json")
assert_eq "$actual" "$expected" "フィクスチャからサマリー生成"

# namespace数の確認
ns_count=$(echo "$actual" | jq '.projects | length')
assert_eq "$ns_count" "3" "サマリーのnamespace数は3"

# alphaのスロット数
alpha_slots=$(echo "$actual" | jq '[.projects[] | select(.namespace == "alpha")] | .[0].slots | length')
assert_eq "$alpha_slots" "2" "alphaのスロット数は2"

# (unset) の存在確認
unset_count=$(echo "$actual" | jq '[.projects[] | select(.namespace == "(unset)")] | length')
assert_eq "$unset_count" "1" "空namespaceは(unset)に変換"

# イベントカウントの確認
alpha_first_total=$(echo "$actual" | jq '[.projects[] | select(.namespace == "alpha")] | .[0].slots[0].total')
assert_eq "$alpha_first_total" "3" "alpha最初のスロットのtotalは3"

alpha_first_up=$(echo "$actual" | jq '[.projects[] | select(.namespace == "alpha")] | .[0].slots[0].user_prompt')
assert_eq "$alpha_first_up" "1" "alpha最初のスロットのuser_promptは1"

# ---------------------------------------------------------------------------
echo "=== format_detail ==="
# ---------------------------------------------------------------------------

PROJECT=""
SINCE="24h"

actual=$(cat "$SCRIPT_DIR/fixtures/sample.jsonl" | format_detail)
expected=$(cat "$SCRIPT_DIR/fixtures/expected_detail.json")
assert_eq "$actual" "$expected" "フィクスチャからディテール生成"

# イベント数の確認
alpha_events=$(echo "$actual" | jq '[.projects[] | select(.namespace == "alpha")] | .[0].events | length')
assert_eq "$alpha_events" "5" "alphaのイベント数は5"

beta_events=$(echo "$actual" | jq '[.projects[] | select(.namespace == "beta")] | .[0].events | length')
assert_eq "$beta_events" "2" "betaのイベント数は2"

# 時系列ソートの確認
first_event=$(echo "$actual" | jq -r '[.projects[] | select(.namespace == "alpha")] | .[0].events[0].timestamp')
last_event=$(echo "$actual" | jq -r '[.projects[] | select(.namespace == "alpha")] | .[0].events[-1].timestamp')
if [[ "$first_event" < "$last_event" ]]; then
  ((PASS++)); echo "  PASS: イベントが時系列順"
else
  ((FAIL++)); echo "  FAIL: イベントが時系列順でない ($first_event >= $last_event)"
fi

# ---------------------------------------------------------------------------
echo "=== empty_response ==="
# ---------------------------------------------------------------------------

SINCE="24h"
PROJECT="test"
MODE="summary"
actual=$(empty_response)
mode_val=$(echo "$actual" | jq -r '.query_params.mode')
projects_len=$(echo "$actual" | jq '.projects | length')
assert_eq "$mode_val" "summary" "空レスポンスのmode"
assert_eq "$projects_len" "0" "空レスポンスのprojectsは空配列"

# ---------------------------------------------------------------------------
echo ""
echo "=== 結果: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
