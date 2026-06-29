#!/usr/bin/env node
// search.js の異常系スモークテスト。
// 実行: node --test test_search.js
// ネットワークも認証情報も不要（引数/env の事前バリデーションで落ちる経路だけを検証する）。

const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");

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

function cleanEnv(extra = {}) {
  const env = { ...process.env };
  delete env.GEMINI_API_KEY;
  delete env.GOOGLE_APPLICATION_CREDENTIALS;
  return { ...env, ...extra };
}

test("引数なしなら usage を出して exit 1", () => {
  const r = run([], { ...process.env, GEMINI_API_KEY: "dummy" });
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /usage/);
});

test("GEMINI_API_KEY と GOOGLE_APPLICATION_CREDENTIALS が両方未設定なら exit 1 で両方案内", () => {
  const r = run(["なにか質問"], cleanEnv());
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /GEMINI_API_KEY/);
  assert.match(r.stderr, /GOOGLE_APPLICATION_CREDENTIALS/);
});

test("GOOGLE_APPLICATION_CREDENTIALS が読めないパスなら exit 2 でファイル読込エラー", () => {
  const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: "/nonexistent/sa.json" }));
  assert.strictEqual(r.status, 2);
  assert.match(r.stderr, /SA キー JSON を読めません/);
});

test("GOOGLE_APPLICATION_CREDENTIALS が壊れた JSON なら exit 2 で解釈エラー", () => {
  const tmp = path.join(os.tmpdir(), `gsearch-test-${process.pid}.json`);
  fs.writeFileSync(tmp, "not a json {");
  try {
    const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: tmp }));
    assert.strictEqual(r.status, 2);
    assert.match(r.stderr, /SA キー JSON を解釈できません/);
  } finally {
    fs.unlinkSync(tmp);
  }
});

test("GOOGLE_APPLICATION_CREDENTIALS の JSON に必須フィールドが無ければ exit 2", () => {
  const tmp = path.join(os.tmpdir(), `gsearch-test-fields-${process.pid}.json`);
  fs.writeFileSync(tmp, JSON.stringify({ client_email: "x@example" })); // private_key / project_id 欠落
  try {
    const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: tmp }));
    assert.strictEqual(r.status, 2);
    assert.match(r.stderr, /client_email \/ private_key \/ project_id/);
  } finally {
    fs.unlinkSync(tmp);
  }
});
