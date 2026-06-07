#!/usr/bin/env node
// gsearch — Gemini API の google_search グラウンディングで web 検索するヘルパー
// usage: node search.js "<質問(自然文)>" [model]
// 環境変数: GEMINI_API_KEY (必須), GEMINI_MODEL (任意, 既定 gemini-3.5-flash)
// このスクリプトはキーを保持しない（env から読むだけ）。

const query = process.argv[2];
const model = process.argv[3] || process.env.GEMINI_MODEL || "gemini-3.5-flash";
const key = process.env.GEMINI_API_KEY;

if (!query) {
  console.error('usage: node search.js "<質問>" [model]');
  process.exit(1);
}
if (!key) {
  console.error("GEMINI_API_KEY が未設定です（env に入れてください）");
  process.exit(1);
}

const body = { contents: [{ parts: [{ text: query }] }], tools: [{ google_search: {} }] };

// grounding の redirect URL を実URLに解決（best-effort）
async function resolveUrl(u) {
  try {
    const r = await fetch(u, { method: "HEAD", redirect: "follow" });
    return r.url || u;
  } catch {
    return u;
  }
}

(async () => {
  let res;
  try {
    res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
      {
        method: "POST",
        headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  } catch (e) {
    console.error("リクエスト失敗:", e.message);
    process.exit(2);
  }

  const j = await res.json();
  if (j.error) {
    console.error("API ERROR:", j.error.message || JSON.stringify(j.error));
    process.exit(2);
  }

  const c = (j.candidates && j.candidates[0]) || {};
  const text = ((c.content && c.content.parts) || [])
    .map((p) => p.text)
    .filter(Boolean)
    .join("\n");
  const gm = c.groundingMetadata || {};

  console.log(text || "(回答テキストなし)");

  console.log("\n--- 検索クエリ (Gemini が自動生成) ---");
  console.log((gm.webSearchQueries || []).join("\n") || "(なし)");

  const chunks = (gm.groundingChunks || []).filter((g) => g.web).slice(0, 8);
  if (chunks.length) {
    const urls = await Promise.all(chunks.map((g) => resolveUrl(g.web.uri)));
    console.log("\n--- ソース ---");
    chunks.forEach((g, i) => console.log(`${i + 1}. ${g.web.title || ""} — ${urls[i]}`));
  }
})();
