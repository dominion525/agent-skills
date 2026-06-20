#!/usr/bin/env node
// gsearch — Gemini API の google_search グラウンディングで web 検索するヘルパー
// usage: node search.js "<質問(自然文)>" [model]
// env: GEMINI_API_KEY (必須), GEMINI_MODEL (任意, 既定 gemini-3.5-flash)
// キーは保持せず env から読むだけ。Node 18+ 必須（global fetch / AbortSignal.timeout）。

const REQUEST_TIMEOUT_MS = 60000; // メイン API
const RESOLVE_TIMEOUT_MS = 5000; //  redirect 解決の HEAD
const MAX_SOURCES = 8;

const query = process.argv[2];
const model = process.argv[3] || process.env.GEMINI_MODEL || "gemini-3.5-flash";
const key = process.env.GEMINI_API_KEY;

function die(msg, code = 1) {
  console.error(msg);
  process.exit(code);
}

if (!query) die('usage: node search.js "<質問>" [model]');
if (!key) die("GEMINI_API_KEY が未設定です（env に入れてください）");
if (typeof fetch !== "function") die("Node 18+ が必要です（global fetch が見つかりません）");

const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
const body = { contents: [{ parts: [{ text: query }] }], tools: [{ google_search: {} }] };

// grounding の redirect URL を実URLに解決（best-effort・タイムアウト付き）
async function resolveUrl(u) {
  try {
    const r = await fetch(u, {
      method: "HEAD",
      redirect: "follow",
      signal: AbortSignal.timeout(RESOLVE_TIMEOUT_MS),
    });
    return r.url || u;
  } catch {
    return u; // 解決できなければ元の redirect URL のまま
  }
}

async function main() {
  // --- API 呼び出し（タイムアウト付き）---
  let res;
  try {
    res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (e) {
    const reason = e?.name === "TimeoutError" ? `タイムアウト(${REQUEST_TIMEOUT_MS / 1000}s)` : e?.message;
    die(`リクエスト失敗: ${reason}`, 2);
  }

  // --- HTTP ステータス確認 ---
  if (!res.ok) {
    const snippet = await res.text().catch(() => "");
    die(`API エラー: HTTP ${res.status} ${res.statusText}\n${snippet.slice(0, 500)}`, 2);
  }

  // --- JSON パース（非JSON応答でも落ちないように）---
  let j;
  try {
    j = await res.json();
  } catch {
    die("API 応答を JSON として解釈できませんでした", 2);
  }
  if (j.error) die(`API ERROR: ${j.error.message || JSON.stringify(j.error)}`, 2);

  const c = (j.candidates && j.candidates[0]) || {};
  const text = ((c.content && c.content.parts) || [])
    .map((p) => p.text)
    .filter(Boolean)
    .join("\n")
    .trim();
  const gm = c.groundingMetadata || {};
  const queries = gm.webSearchQueries || [];

  // --- 回答（空なら理由を出す）---
  if (text) {
    console.log(text);
  } else {
    console.log(`(回答テキストなし${c.finishReason ? ` / finishReason: ${c.finishReason}` : ""})`);
  }

  // --- 接地シグナル：実際に検索されたか ---
  if (queries.length === 0) {
    console.log("\n※ web 検索が実行されていない可能性があります（未接地の回答かもしれません）");
  }

  // --- Gemini が組んだ検索クエリ ---
  console.log("\n--- 検索クエリ (Gemini が自動生成) ---");
  console.log(queries.join("\n") || "(なし)");

  // --- ソース ---
  console.log("\n--- ソース ---");
  const chunks = (gm.groundingChunks || []).filter((g) => g.web?.uri).slice(0, MAX_SOURCES);
  if (chunks.length) {
    const urls = await Promise.all(chunks.map((g) => resolveUrl(g.web.uri)));
    chunks.forEach((g, i) => console.log(`${i + 1}. ${g.web.title || ""} — ${urls[i]}`));
  } else {
    console.log("(参照ソースなし)");
  }
}

main().catch((e) => die(`予期せぬエラー: ${e?.message || e}`, 2));
