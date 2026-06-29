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
// CLI 起動時は require.main === module で main を実行する。本体ロジックは export して
// テストから fetch を注入できるようにしてある。

const { webcrypto } = require("node:crypto");
const fs = require("node:fs");

const REQUEST_TIMEOUT_MS = 60000; // メイン API
const OAUTH_TIMEOUT_MS = 15000; //   OAuth2 token 取得
const RESOLVE_TIMEOUT_MS = 5000; //   redirect 解決の HEAD
const MAX_SOURCES = 8;

// 経路ごとの既定モデル。GEMINI_MODEL env と argv[3] はどちらも上書きする。
// Vertex AI 側は AI Studio とラインナップがずれていて gemini-3.5-flash は 404。
// 将来 Vertex AI 側で同名が公開されたらここを 1 行差し替えれば追従できる。
const DEFAULT_MODELS = {
  aistudio: "gemini-3.5-flash",
  vertex: "gemini-2.5-flash",
};

// CLI 用の構造化エラー。throw で die() の代わりに使い、最上位で exit code を取り出す。
class GsearchError extends Error {
  constructor(msg, exitCode = 1) {
    super(msg);
    this.exitCode = exitCode;
  }
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
async function getVertexAccessToken(saPath, { fetch: fetchImpl = globalThis.fetch, now = () => Date.now() } = {}) {
  let raw;
  try {
    raw = fs.readFileSync(saPath, "utf8");
  } catch (e) {
    throw new GsearchError(`SA キー JSON を読めません (${saPath}): ${e?.message || e}`, 2);
  }
  let sa;
  try {
    sa = JSON.parse(raw);
  } catch (e) {
    throw new GsearchError(`SA キー JSON を解釈できません (${saPath}): ${e?.message || e}`, 2);
  }
  if (!sa.client_email || !sa.private_key || !sa.project_id) {
    throw new GsearchError("SA キー JSON に client_email / private_key / project_id が揃っていません", 2);
  }

  const iat = Math.floor(now() / 1000);
  const claims = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/cloud-platform",
    aud: "https://oauth2.googleapis.com/token",
    iat,
    exp: iat + 3600,
  };

  let jwt;
  try {
    jwt = await signJwtRs256(claims, sa.private_key);
  } catch (e) {
    throw new GsearchError(`JWT 署名に失敗しました: ${e?.message || e}`, 2);
  }

  let res;
  try {
    res = await fetchImpl("https://oauth2.googleapis.com/token", {
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
    throw new GsearchError(`OAuth2 トークン取得に失敗: ${reason}`, 2);
  }
  if (!res.ok) {
    const snippet = await res.text().catch(() => "");
    throw new GsearchError(`OAuth2 トークン取得失敗: HTTP ${res.status} ${res.statusText}\n${snippet.slice(0, 500)}`, 2);
  }
  const tok = await res.json().catch(() => ({}));
  if (!tok.access_token) throw new GsearchError("OAuth2 応答に access_token が含まれていません", 2);
  return { accessToken: tok.access_token, projectId: sa.project_id };
}

// --- generateContent 呼び出し（共通エラーハンドリング）---
async function doGenerate(endpoint, headers, body, { fetch: fetchImpl = globalThis.fetch } = {}) {
  let res;
  try {
    res = await fetchImpl(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (e) {
    const reason = e?.name === "TimeoutError" ? `タイムアウト(${REQUEST_TIMEOUT_MS / 1000}s)` : e?.message;
    throw new GsearchError(`リクエスト失敗: ${reason}`, 2);
  }
  if (!res.ok) {
    const snippet = await res.text().catch(() => "");
    throw new GsearchError(`API エラー: HTTP ${res.status} ${res.statusText}\n${snippet.slice(0, 500)}`, 2);
  }
  let j;
  try {
    j = await res.json();
  } catch {
    throw new GsearchError("API 応答を JSON として解釈できませんでした", 2);
  }
  if (j.error) throw new GsearchError(`API ERROR: ${j.error.message || JSON.stringify(j.error)}`, 2);
  return j;
}

// --- AI Studio 経路 ---
async function callAIStudio({ apiKey, model, query }, opts = {}) {
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  const headers = { "x-goog-api-key": apiKey, "Content-Type": "application/json" };
  const body = { contents: [{ parts: [{ text: query }] }], tools: [{ google_search: {} }] };
  return doGenerate(endpoint, headers, body, opts);
}

// --- Vertex AI 経路 ---
async function callVertex({ credPath, location, model, query }, opts = {}) {
  const { accessToken, projectId } = await getVertexAccessToken(credPath, opts);
  const endpoint = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/publishers/google/models/${model}:generateContent`;
  const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
  const body = {
    contents: [{ role: "user", parts: [{ text: query }] }],
    tools: [{ googleSearch: {} }],
  };
  return doGenerate(endpoint, headers, body, opts);
}

// grounding の redirect URL を実URLに解決（best-effort・タイムアウト付き）
async function resolveUrl(u, { fetch: fetchImpl = globalThis.fetch } = {}) {
  try {
    const r = await fetchImpl(u, {
      method: "HEAD",
      redirect: "follow",
      signal: AbortSignal.timeout(RESOLVE_TIMEOUT_MS),
    });
    return r.url || u;
  } catch {
    return u; // 解決できなければ元の redirect URL のまま
  }
}

// 認証経路を env から判定する。両方ある場合は AI Studio を優先する。
function selectMode(env) {
  if (env.GEMINI_API_KEY) return "aistudio";
  if (env.GOOGLE_APPLICATION_CREDENTIALS) return "vertex";
  return null;
}

// 応答 → 標準出力整形（log() を差し替えるとテスト時に出力をキャプチャできる）
async function formatOutput(j, { log = (s) => console.log(s), opts = {} } = {}) {
  const c = (j.candidates && j.candidates[0]) || {};
  const text = ((c.content && c.content.parts) || [])
    .map((p) => p.text)
    .filter(Boolean)
    .join("\n")
    .trim();
  const gm = c.groundingMetadata || {};
  const queries = gm.webSearchQueries || [];

  if (text) {
    log(text);
  } else {
    log(`(回答テキストなし${c.finishReason ? ` / finishReason: ${c.finishReason}` : ""})`);
  }
  if (queries.length === 0) {
    log("\n※ web 検索が実行されていない可能性があります（未接地の回答かもしれません）");
  }
  log("\n--- 検索クエリ (Gemini が自動生成) ---");
  log(queries.join("\n") || "(なし)");
  log("\n--- ソース ---");
  const chunks = (gm.groundingChunks || []).filter((g) => g.web?.uri).slice(0, MAX_SOURCES);
  if (chunks.length) {
    const urls = await Promise.all(chunks.map((g) => resolveUrl(g.web.uri, opts)));
    chunks.forEach((g, i) => log(`${i + 1}. ${g.web.title || ""} — ${urls[i]}`));
  } else {
    log("(参照ソースなし)");
  }
}

// argv + env を受け取って一連の処理を実行する。CLI からも単体テストからも呼ぶ。
async function runMain({ argv, env, log = (s) => console.log(s), opts = {} } = {}) {
  const query = argv[2];
  const modelArg = argv[3];
  if (!query) throw new GsearchError('usage: node search.js "<質問>" [model]');
  if (typeof (opts.fetch || globalThis.fetch) !== "function") {
    throw new GsearchError("Node 18+ が必要です（global fetch が見つかりません）");
  }
  const mode = selectMode(env);
  if (!mode) {
    throw new GsearchError(
      "認証情報が見つかりません。次のいずれかを env にセットしてください:\n" +
        "  - GEMINI_API_KEY                 : AI Studio キー\n" +
        "  - GOOGLE_APPLICATION_CREDENTIALS : Vertex AI サービスアカウント JSON のパス",
    );
  }
  const model = modelArg || env.GEMINI_MODEL || DEFAULT_MODELS[mode];

  const j =
    mode === "aistudio"
      ? await callAIStudio({ apiKey: env.GEMINI_API_KEY, model, query }, opts)
      : await callVertex(
          {
            credPath: env.GOOGLE_APPLICATION_CREDENTIALS,
            location: env.GEMINI_LOCATION || "us-central1",
            model,
            query,
          },
          opts,
        );

  await formatOutput(j, { log, opts });
}

if (require.main === module) {
  runMain({ argv: process.argv, env: process.env }).catch((e) => {
    if (e instanceof GsearchError) {
      console.error(e.message);
      process.exit(e.exitCode);
    }
    console.error(`予期せぬエラー: ${e?.message || e}`);
    process.exit(2);
  });
}

module.exports = {
  DEFAULT_MODELS,
  GsearchError,
  b64urlFromBuffer,
  b64urlFromString,
  signJwtRs256,
  getVertexAccessToken,
  doGenerate,
  callAIStudio,
  callVertex,
  resolveUrl,
  selectMode,
  formatOutput,
  runMain,
};
