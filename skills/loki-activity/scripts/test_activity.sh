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
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label"
    diff <(echo "$actual") <(echo "$expected") || true
  fi
}

assert_contains() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if echo "$actual" | grep -q "$expected"; then
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label (expected to contain: $expected)"
  fi
}

assert_exit_code() {
  local label="$1"
  local expected_code="$2"
  shift 2
  local actual_code=0
  "$@" > /dev/null 2>&1 || actual_code=$?
  if [[ "$actual_code" == "$expected_code" ]]; then
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label (expected exit $expected_code, got $actual_code)"
  fi
}

# ---------------------------------------------------------------------------
echo "=== build_query ==="
# ---------------------------------------------------------------------------

actual=$(build_query "")
assert_eq "$actual" '{service_name="claude-code"}' "全件クエリ（PROJECT空）"

actual=$(build_query "sandbox")
assert_eq "$actual" '{service_name="claude-code", service_namespace=~".*sandbox.*"}' "フィルタクエリ（PROJECT=sandbox）"

actual=$(build_query "alpha-project")
assert_eq "$actual" '{service_name="claude-code", service_namespace=~".*alpha-project.*"}' "フィルタクエリ（ハイフン含む）"

# ---------------------------------------------------------------------------
echo "=== parse_args ==="
# ---------------------------------------------------------------------------

# 基本的な引数パース
SINCE="24h"; PROJECT=""; ALL=false; MODE="summary"; INTERVAL=10
parse_args --since 48h --project myproj --detail --interval 5
assert_eq "$SINCE" "48h" "parse_args: --since"
assert_eq "$PROJECT" "myproj" "parse_args: --project"
assert_eq "$MODE" "detail" "parse_args: --detail"
assert_eq "$INTERVAL" "5" "parse_args: --interval"

# --all フラグ
SINCE="24h"; PROJECT=""; ALL=false; MODE="summary"; INTERVAL=10
parse_args --all
assert_eq "$ALL" "true" "parse_args: --all"

# デフォルト値（引数なし）
SINCE="24h"; PROJECT=""; ALL=false; MODE="summary"; INTERVAL=10
parse_args
assert_eq "$SINCE" "24h" "parse_args: デフォルトsince"
assert_eq "$MODE" "summary" "parse_args: デフォルトmode"

# 不正なINTERVAL
assert_exit_code "parse_args: INTERVAL=0 はエラー" 1 bash -c 'source activity.sh; parse_args --interval 0'
assert_exit_code "parse_args: INTERVAL=abc はエラー" 1 bash -c 'source activity.sh; parse_args --interval abc'
assert_exit_code "parse_args: INTERVAL=-5 はエラー" 1 bash -c 'source activity.sh; parse_args --interval -5'

# 値なしオプション
assert_exit_code "parse_args: --since 値なし" 1 bash -c 'source activity.sh; parse_args --since'
assert_exit_code "parse_args: --project 値なし" 1 bash -c 'source activity.sh; parse_args --project'

# 不明なオプション
assert_exit_code "parse_args: 不明オプション" 1 bash -c 'source activity.sh; parse_args --unknown'

# ---------------------------------------------------------------------------
echo "=== empty_response ==="
# ---------------------------------------------------------------------------

actual=$(empty_response "24h" "test" "summary")
assert_eq "$(echo "$actual" | jq -r '.query_params.mode')" "summary" "empty_responseのmode"
assert_eq "$(echo "$actual" | jq '.projects | length')" "0" "empty_responseのprojectsは空配列"
assert_eq "$(echo "$actual" | jq -r '.query_params.project_filter')" "test" "empty_responseのproject_filter"
assert_eq "$(echo "$actual" | jq -r '.query_params.since')" "24h" "empty_responseのsince"

# JSON妥当性の確認
echo "$actual" | jq . > /dev/null 2>&1
PASS=$((PASS + 1)); echo "  PASS: empty_responseのJSON妥当性"

# 特殊文字を含むプロジェクト名
actual=$(empty_response "24h" 'test"project' "summary")
echo "$actual" | jq . > /dev/null 2>&1
PASS=$((PASS + 1)); echo "  PASS: empty_response 特殊文字プロジェクト名のJSON妥当性"

# ---------------------------------------------------------------------------
echo "=== format_summary ==="
# ---------------------------------------------------------------------------

actual=$(cat "$SCRIPT_DIR/fixtures/sample.jsonl" | format_summary "24h" "" 10)
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

# 空入力テスト
actual=$(echo -n "" | format_summary "24h" "" 10 2>&1 || true)
assert_eq "$(echo "$actual" | jq '.projects | length')" "0" "空入力のサマリーはprojects空"

# ---------------------------------------------------------------------------
echo "=== format_detail ==="
# ---------------------------------------------------------------------------

actual=$(cat "$SCRIPT_DIR/fixtures/sample.jsonl" | format_detail "24h" "")
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
  PASS=$((PASS + 1)); echo "  PASS: イベントが時系列順"
else
  FAIL=$((FAIL + 1)); echo "  FAIL: イベントが時系列順でない ($first_event >= $last_event)"
fi

# 空入力テスト
actual=$(echo -n "" | format_detail "24h" "" 2>&1 || true)
assert_eq "$(echo "$actual" | jq '.projects | length')" "0" "空入力のディテールはprojects空"

# ---------------------------------------------------------------------------
echo ""
echo "=== 結果: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
