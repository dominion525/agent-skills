#!/usr/bin/env node
// search.js の異常系スモークテスト。
// 実行: node --test test_search.js
// ネットワークも GEMINI_API_KEY も不要（引数/キーの事前バリデーションで落ちる経路だけを検証する）。

const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

const SCRIPT = path.join(__dirname, "search.js");

// search.js を起動し { status, stdout, stderr } を返す。
// 非ゼロ終了でも例外にせず結果を取り出す。env は呼び出し側で完全に差し替える。
function run(args, env) {
  try {
    const stdout = execFileSync("node", [SCRIPT, ...args], {
      env,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return { status: 0, stdout, stderr: "" };
  } catch (e) {
    return { status: e.status, stdout: e.stdout || "", stderr: e.stderr || "" };
  }
}

test("引数なしなら usage を出して exit 1", () => {
  const r = run([], { ...process.env, GEMINI_API_KEY: "dummy" });
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /usage/);
});

test("GEMINI_API_KEY 未設定なら exit 1 でキー不足を知らせる", () => {
  const env = { ...process.env };
  delete env.GEMINI_API_KEY;
  const r = run(["なにか質問"], env);
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /GEMINI_API_KEY/);
});
