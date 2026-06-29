#!/usr/bin/env node
// gsearch — Gemini API の google_search グラウンディングで web 検索するヘルパー
// usage: node search.js "<質問(自然文)>" [model]
//
// 認証経路は env で自動判定する:
//   1. GEMINI_API_KEY            → AI Studio (generativelanguage.googleapis.com)
//   2. GOOGLE_APPLICATION_CREDENTIALS (SA キー JSON のパス) → Vertex AI
//        - PROJECT_ID は SA キー JSON の project_id から取得
//        - LOCATION  は env GEMINI_LOCATION (既定 us-central1)
//   3. どちらも未設定 → エラー終了
//
// その他 env:
//   - GEMINI_MODEL : モデル名上書き (既定 gemini-3.5-flash)
//
// キーは保持せず env から読むだけ。Node 18+ 必須（global fetch / webcrypto / AbortSignal.timeout）。

const { webcrypto } = require("node:crypto");
const fs = require("node:fs");

const REQUEST_TIMEOUT_MS = 60000; // メイン API
const OAUTH_TIMEOUT_MS = 15000; //   OAuth2 token 取得
const RESOLVE_TIMEOUT_MS = 5000; //   redirect 解決の HEAD
const MAX_SOURCES = 8;

const query = process.argv[2];
const modelArg = process.argv[3];
const apiKey = process.env.GEMINI_API_KEY;
const credPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
const location = process.env.GEMINI_LOCATION || "us-central1";
const model = modelArg || process.env.GEMINI_MODEL || "gemini-3.5-flash";

function die(msg, code = 1) {
  console.error(msg);
  process.exit(code);
}

if (!query) die('usage: node search.js "<質問>" [model]');
if (typeof fetch !== "function") die("Node 18+ が必要です（global fetch が見つかりません）");

// --- 認証経路の判定 ---
let mode;
if (apiKey) {
  mode = "aistudio";
} else if (credPath) {
  mode = "vertex";
} else {
  die(
    "認証情報が見つかりません。次のいずれかを env にセットしてください:\n" +
      "  - GEMINI_API_KEY                 : AI Studio キー\n" +
      "  - GOOGLE_APPLICATION_CREDENTIALS : Vertex AI サービスアカウント JSON のパス",
  );
}

// --- base64url ヘルパー ---
function b64urlFromBuffer(buf) {
  return Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlFromString(str) {
  return b64urlFromBuffer(Buffer.from(str, "utf8"));
}

// --- SA キー → RS256 JWT 署名（webcrypto, 外部依存なし）---
async function signJwtRs256(claims, privateKeyPem) {
  const pemBody = privateKeyPem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  if (!pemBody) throw new Error("SA キーの private_key が空です");
  const keyBuf = Buffer.from(pemBody, "base64");
  const cryptoKey = await webcrypto.subtle.importKey(
    "pkcs8",
    keyBuf,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const header = { alg: "RS256", typ: "JWT" };
  const signingInput = `${b64urlFromString(JSON.stringify(header))}.${b64urlFromString(JSON.stringify(claims))}`;
  const sig = await webcrypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    cryptoKey,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${b64urlFromBuffer(sig)}`;
}

// --- SA キー JSON → access token（jwt-bearer grant 交換）---
async function getVertexAccessToken(saPath) {
  let raw;
  try {
    raw = fs.readFileSync(saPath, "utf8");
  } catch (e) {
    die(`SA キー JSON を読めません (${saPath}): ${e?.message || e}`, 2);
  }
  let sa;
  try {
    sa = JSON.parse(raw);
  } catch (e) {
    die(`SA キー JSON を解釈できません (${saPath}): ${e?.message || e}`, 2);
  }
  if (!sa.client_email || !sa.private_key || !sa.project_id) {
    die("SA キー JSON に client_email / private_key / project_id が揃っていません", 2);
  }

  const now = Math.floor(Date.now() / 1000);
  const claims = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/cloud-platform",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };

  let jwt;
  try {
    jwt = await signJwtRs256(claims, sa.private_key);
  } catch (e) {
    die(`JWT 署名に失敗しました: ${e?.message || e}`, 2);
  }

  let res;
  try {
    res = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
        assertion: jwt,
      }).toString(),
      signal: AbortSignal.timeout(OAUTH_TIMEOUT_MS),
    });
  } catch (e) {
    const reason = e?.name === "TimeoutError" ? `タイムアウト(${OAUTH_TIMEOUT_MS / 1000}s)` : e?.message;
    die(`OAuth2 トークン取得に失敗: ${reason}`, 2);
  }
  if (!res.ok) {
    const snippet = await res.text().catch(() => "");
    die(`OAuth2 トークン取得失敗: HTTP ${res.status} ${res.statusText}\n${snippet.slice(0, 500)}`, 2);
  }
  const tok = await res.json().catch(() => ({}));
  if (!tok.access_token) die("OAuth2 応答に access_token が含まれていません", 2);
  return { accessToken: tok.access_token, projectId: sa.project_id };
}

// --- AI Studio 経路 ---
async function callAIStudio() {
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  const headers = { "x-goog-api-key": apiKey, "Content-Type": "application/json" };
  const body = { contents: [{ parts: [{ text: query }] }], tools: [{ google_search: {} }] };
  return doGenerate(endpoint, headers, body);
}

// --- Vertex AI 経路 ---
async function callVertex() {
  const { accessToken, projectId } = await getVertexAccessToken(credPath);
  const endpoint = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/publishers/google/models/${model}:generateContent`;
  const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
  const body = {
    contents: [{ role: "user", parts: [{ text: query }] }],
    tools: [{ googleSearch: {} }],
  };
  return doGenerate(endpoint, headers, body);
}

// --- generateContent 呼び出し（共通エラーハンドリング）---
async function doGenerate(endpoint, headers, body) {
  let res;
  try {
    res = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (e) {
    const reason = e?.name === "TimeoutError" ? `タイムアウト(${REQUEST_TIMEOUT_MS / 1000}s)` : e?.message;
    die(`リクエスト失敗: ${reason}`, 2);
  }
  if (!res.ok) {
    const snippet = await res.text().catch(() => "");
    die(`API エラー: HTTP ${res.status} ${res.statusText}\n${snippet.slice(0, 500)}`, 2);
  }
  let j;
  try {
    j = await res.json();
  } catch {
    die("API 応答を JSON として解釈できませんでした", 2);
  }
  if (j.error) die(`API ERROR: ${j.error.message || JSON.stringify(j.error)}`, 2);
  return j;
}

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
  const j = mode === "aistudio" ? await callAIStudio() : await callVertex();

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
