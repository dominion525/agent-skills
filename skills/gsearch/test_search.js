#!/usr/bin/env node
// search.js のテスト。
// 実行: node --test test_search.js
//
// 構成:
//   1. CLI スモーク (execFileSync) — argv/env バリデーションが exit code に反映されるか
//   2. 単体テスト (require) — 本体関数を fetch スタブ + 一時 RSA キーで触る
//
// ネットワークも認証情報も不要。RSA キーはテスト内で生成して JWT 署名を public key で検証する。

const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const crypto = require("node:crypto");

const SCRIPT = path.join(__dirname, "search.js");
const mod = require("./search.js");

// search.js を子プロセスで起動し { status, stdout, stderr } を返す。
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

// 一時ファイルを作って fn に渡し、後始末する。
function withTmpFile(content, fn) {
  const tmp = path.join(os.tmpdir(), `gsearch-test-${process.pid}-${Math.floor(Math.random() * 1e9)}.json`);
  fs.writeFileSync(tmp, content);
  try {
    return fn(tmp);
  } finally {
    try {
      fs.unlinkSync(tmp);
    } catch {
      // すでに消えていれば無視
    }
  }
}

// 2048-bit RSA を生成して PKCS8 PEM と public key オブジェクトを返す。
function genTestRsa() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ format: "pem", type: "pkcs8" });
  return { pem, publicKey };
}

// fetch スタブ。呼び出しを順に records に蓄積、handler が決めたレスポンスを返す。
function makeFetchStub(handler) {
  const records = [];
  const stub = async (url, init) => {
    records.push({ url, init });
    return handler(url, init, records.length - 1);
  };
  stub.records = records;
  return stub;
}

// 最低限のレスポンスオブジェクトを組む。
function fetchResponse({ ok = true, status = 200, statusText = "OK", json = null, text = "", url = "" } = {}) {
  return {
    ok,
    status,
    statusText,
    url,
    json: async () => json,
    text: async () => text,
  };
}

// ============================================================================
// 1. CLI スモークテスト (execFileSync)
// ============================================================================

test("CLI: 引数なしなら usage を出して exit 1", () => {
  const r = run([], { ...process.env, GEMINI_API_KEY: "dummy" });
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /usage/);
});

test("CLI: GEMINI_API_KEY と GOOGLE_APPLICATION_CREDENTIALS が両方未設定なら exit 1 で両方案内", () => {
  const r = run(["なにか質問"], cleanEnv());
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /GEMINI_API_KEY/);
  assert.match(r.stderr, /GOOGLE_APPLICATION_CREDENTIALS/);
});

test("CLI: GOOGLE_APPLICATION_CREDENTIALS が読めないパスなら exit 2", () => {
  const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: "/nonexistent/sa.json" }));
  assert.strictEqual(r.status, 2);
  assert.match(r.stderr, /SA キー JSON を読めません/);
});

test("CLI: GOOGLE_APPLICATION_CREDENTIALS が壊れた JSON なら exit 2", () => {
  withTmpFile("not a json {", (tmp) => {
    const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: tmp }));
    assert.strictEqual(r.status, 2);
    assert.match(r.stderr, /SA キー JSON を解釈できません/);
  });
});

test("CLI: GOOGLE_APPLICATION_CREDENTIALS の JSON に必須フィールドが無ければ exit 2", () => {
  withTmpFile(JSON.stringify({ client_email: "x@example" }), (tmp) => {
    const r = run(["なにか質問"], cleanEnv({ GOOGLE_APPLICATION_CREDENTIALS: tmp }));
    assert.strictEqual(r.status, 2);
    assert.match(r.stderr, /client_email \/ private_key \/ project_id/);
  });
});

// ============================================================================
// 2. b64url ヘルパー
// ============================================================================

test("b64urlFromString: RFC 4648 のテストベクタ", () => {
  // 「foob」のような長さで padding が落ちることを確認する。URL 安全文字は別テスト。
  assert.strictEqual(mod.b64urlFromString(""), "");
  assert.strictEqual(mod.b64urlFromString("f"), "Zg");
  assert.strictEqual(mod.b64urlFromString("fo"), "Zm8");
  assert.strictEqual(mod.b64urlFromString("foo"), "Zm9v");
  assert.strictEqual(mod.b64urlFromString("foob"), "Zm9vYg");
  assert.strictEqual(mod.b64urlFromString("fooba"), "Zm9vYmE");
  assert.strictEqual(mod.b64urlFromString("foobar"), "Zm9vYmFy");
});

test("b64urlFromBuffer: + と / が - と _ に置換される", () => {
  // 0xFB 0xFF 0xBF → 「+/+」相当の出力になるバイト列。
  const buf = Buffer.from([0xfb, 0xff, 0xbf]);
  const out = mod.b64urlFromBuffer(buf);
  assert.doesNotMatch(out, /[+/=]/);
  // base64 (標準) と URL-safe で同値のはず。
  const stdB64 = Buffer.from([0xfb, 0xff, 0xbf]).toString("base64").replace(/=+$/, "");
  assert.strictEqual(out, stdB64.replace(/\+/g, "-").replace(/\//g, "_"));
});

// ============================================================================
// 3. signJwtRs256
// ============================================================================

test("signJwtRs256: 3 セグメントの JWT を返し、公開鍵で署名検証できる", async () => {
  const { pem, publicKey } = genTestRsa();
  const claims = { iss: "x@example.com", scope: "test-scope", aud: "https://example.com", iat: 1700000000, exp: 1700003600 };
  const jwt = await mod.signJwtRs256(claims, pem);
  const parts = jwt.split(".");
  assert.strictEqual(parts.length, 3, "header.claims.sig の 3 セグメント");

  // header
  const header = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  assert.deepStrictEqual(header, { alg: "RS256", typ: "JWT" });

  // claims
  const decoded = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
  assert.deepStrictEqual(decoded, claims);

  // 署名検証
  const verify = crypto.createVerify("RSA-SHA256");
  verify.update(`${parts[0]}.${parts[1]}`);
  const sigBytes = Buffer.from(parts[2], "base64url");
  assert.ok(verify.verify(publicKey, sigBytes), "RSA-SHA256 署名検証が成功する");
  assert.strictEqual(sigBytes.length, 256, "2048-bit RSA 署名は 256 byte");
});

test("signJwtRs256: PEM body が空なら throw", async () => {
  await assert.rejects(
    () => mod.signJwtRs256({}, "-----BEGIN PRIVATE KEY-----\n-----END PRIVATE KEY-----"),
    /private_key が空/,
  );
});

// ============================================================================
// 4. selectMode
// ============================================================================

test("selectMode: GEMINI_API_KEY だけ → aistudio", () => {
  assert.strictEqual(mod.selectMode({ GEMINI_API_KEY: "K" }), "aistudio");
});

test("selectMode: GOOGLE_APPLICATION_CREDENTIALS だけ → vertex", () => {
  assert.strictEqual(mod.selectMode({ GOOGLE_APPLICATION_CREDENTIALS: "/p" }), "vertex");
});

test("selectMode: 両方ある場合は AI Studio を優先", () => {
  assert.strictEqual(
    mod.selectMode({ GEMINI_API_KEY: "K", GOOGLE_APPLICATION_CREDENTIALS: "/p" }),
    "aistudio",
  );
});

test("selectMode: どちらも無ければ null", () => {
  assert.strictEqual(mod.selectMode({}), null);
});

// ============================================================================
// 5. callAIStudio / callVertex / getVertexAccessToken (fetch スタブ)
// ============================================================================

test("callAIStudio: 期待 URL / ヘッダ / body (tools.google_search) で fetch する", async () => {
  const fakeJson = { candidates: [{ content: { parts: [{ text: "answer" }] } }] };
  const stub = makeFetchStub(() => fetchResponse({ json: fakeJson }));
  const j = await mod.callAIStudio({ apiKey: "KEY", model: "M", query: "Q" }, { fetch: stub });
  assert.deepStrictEqual(j, fakeJson);
  assert.strictEqual(stub.records.length, 1);
  const { url, init } = stub.records[0];
  assert.strictEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/M:generateContent");
  assert.strictEqual(init.method, "POST");
  assert.strictEqual(init.headers["x-goog-api-key"], "KEY");
  const body = JSON.parse(init.body);
  assert.deepStrictEqual(body.tools, [{ google_search: {} }]);
  assert.strictEqual(body.contents[0].parts[0].text, "Q");
});

test("getVertexAccessToken: SA → JWT → token 交換、access_token と project_id を返す", async () => {
  const { pem } = genTestRsa();
  const sa = { client_email: "svc@example.iam.gserviceaccount.com", private_key: pem, project_id: "PROJ-1" };
  await withTmpFile(JSON.stringify(sa), async (tmp) => {
    const stub = makeFetchStub(() => fetchResponse({ json: { access_token: "TOK", token_type: "Bearer" } }));
    const result = await mod.getVertexAccessToken(tmp, { fetch: stub, now: () => 1_700_000_000_000 });
    assert.strictEqual(result.accessToken, "TOK");
    assert.strictEqual(result.projectId, "PROJ-1");
    const { url, init } = stub.records[0];
    assert.strictEqual(url, "https://oauth2.googleapis.com/token");
    const form = new URLSearchParams(init.body);
    assert.strictEqual(form.get("grant_type"), "urn:ietf:params:oauth:grant-type:jwt-bearer");
    const assertion = form.get("assertion");
    const segs = assertion.split(".");
    assert.strictEqual(segs.length, 3);
    const claims = JSON.parse(Buffer.from(segs[1], "base64url").toString("utf8"));
    assert.strictEqual(claims.iss, sa.client_email);
    assert.strictEqual(claims.aud, "https://oauth2.googleapis.com/token");
    assert.strictEqual(claims.scope, "https://www.googleapis.com/auth/cloud-platform");
    assert.strictEqual(claims.iat, 1_700_000_000);
    assert.strictEqual(claims.exp, 1_700_000_000 + 3600);
  });
});

test("getVertexAccessToken: OAuth が 4xx を返したら GsearchError(2)", async () => {
  const { pem } = genTestRsa();
  const sa = { client_email: "x@example", private_key: pem, project_id: "P" };
  await withTmpFile(JSON.stringify(sa), async (tmp) => {
    const stub = makeFetchStub(() => fetchResponse({ ok: false, status: 401, statusText: "Unauthorized", text: "no" }));
    await assert.rejects(() => mod.getVertexAccessToken(tmp, { fetch: stub }), (e) => {
      return e instanceof mod.GsearchError && e.exitCode === 2 && /OAuth2 トークン取得失敗/.test(e.message);
    });
  });
});

test("getVertexAccessToken: access_token が無い応答なら GsearchError(2)", async () => {
  const { pem } = genTestRsa();
  const sa = { client_email: "x@example", private_key: pem, project_id: "P" };
  await withTmpFile(JSON.stringify(sa), async (tmp) => {
    const stub = makeFetchStub(() => fetchResponse({ json: { /* access_token なし */ } }));
    await assert.rejects(() => mod.getVertexAccessToken(tmp, { fetch: stub }), /access_token/);
  });
});

test("callVertex: 期待 URL / Authorization / body (tools.googleSearch camelCase)", async () => {
  const { pem } = genTestRsa();
  const sa = { client_email: "svc@example", private_key: pem, project_id: "PROJ" };
  await withTmpFile(JSON.stringify(sa), async (tmp) => {
    const fakeJson = { candidates: [{ content: { parts: [{ text: "v" }] } }] };
    const stub = makeFetchStub((url) => {
      if (url === "https://oauth2.googleapis.com/token") {
        return fetchResponse({ json: { access_token: "VTOK" } });
      }
      return fetchResponse({ json: fakeJson });
    });
    const j = await mod.callVertex(
      { credPath: tmp, location: "asia-northeast1", model: "gemini-2.5-flash", query: "Q" },
      { fetch: stub },
    );
    assert.deepStrictEqual(j, fakeJson);
    assert.strictEqual(stub.records.length, 2);
    const generate = stub.records[1];
    assert.strictEqual(
      generate.url,
      "https://asia-northeast1-aiplatform.googleapis.com/v1/projects/PROJ/locations/asia-northeast1/publishers/google/models/gemini-2.5-flash:generateContent",
    );
    assert.strictEqual(generate.init.headers.Authorization, "Bearer VTOK");
    const body = JSON.parse(generate.init.body);
    assert.deepStrictEqual(body.tools, [{ googleSearch: {} }]);
    assert.strictEqual(body.contents[0].role, "user");
    assert.strictEqual(body.contents[0].parts[0].text, "Q");
  });
});

// ============================================================================
// 6. doGenerate のエラー経路
// ============================================================================

test("doGenerate: HTTP 4xx で GsearchError(2)", async () => {
  const stub = makeFetchStub(() => fetchResponse({ ok: false, status: 400, statusText: "Bad", text: "broken" }));
  await assert.rejects(() => mod.doGenerate("https://x", {}, {}, { fetch: stub }), (e) => {
    return e instanceof mod.GsearchError && e.exitCode === 2 && /HTTP 400/.test(e.message);
  });
});

test("doGenerate: 応答が JSON にならないなら GsearchError(2)", async () => {
  const stub = makeFetchStub(() =>
    fetchResponse({ json: null }),
  );
  // json() を強制的に throw する応答に差し替える
  stub.records.length = 0;
  const stub2 = async () => ({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => {
      throw new Error("invalid json");
    },
    text: async () => "",
  });
  await assert.rejects(() => mod.doGenerate("https://x", {}, {}, { fetch: stub2 }), /JSON として解釈/);
});

test("doGenerate: 応答に error フィールドがあったら GsearchError(2)", async () => {
  const stub = makeFetchStub(() => fetchResponse({ json: { error: { message: "boom" } } }));
  await assert.rejects(() => mod.doGenerate("https://x", {}, {}, { fetch: stub }), /API ERROR: boom/);
});

// ============================================================================
// 7. resolveUrl
// ============================================================================

test("resolveUrl: HEAD で redirect 解決 → 解決後の URL を返す", async () => {
  const stub = makeFetchStub(() => fetchResponse({ url: "https://final.example/page" }));
  const out = await mod.resolveUrl("https://redirect.example/r", { fetch: stub });
  assert.strictEqual(out, "https://final.example/page");
  assert.strictEqual(stub.records[0].init.method, "HEAD");
  assert.strictEqual(stub.records[0].init.redirect, "follow");
});

test("resolveUrl: fetch が throw したら元 URL を返す (best-effort)", async () => {
  const stub = async () => {
    throw new Error("network down");
  };
  const out = await mod.resolveUrl("https://original.example/x", { fetch: stub });
  assert.strictEqual(out, "https://original.example/x");
});

// ============================================================================
// 8. formatOutput
// ============================================================================

test("formatOutput: text / 検索クエリ / ソースを順に log() に出す", async () => {
  const logs = [];
  const j = {
    candidates: [
      {
        content: { parts: [{ text: "ANSWER" }] },
        groundingMetadata: {
          webSearchQueries: ["q1", "q2"],
          groundingChunks: [
            { web: { uri: "https://a.example", title: "A" } },
            { web: { uri: "https://b.example", title: "B" } },
          ],
        },
      },
    ],
  };
  // resolveUrl 内の fetch を 200 HEAD として返す
  const stub = makeFetchStub((u) => fetchResponse({ url: u }));
  await mod.formatOutput(j, { log: (s) => logs.push(s), opts: { fetch: stub } });
  const joined = logs.join("\n");
  assert.match(joined, /^ANSWER/);
  assert.match(joined, /検索クエリ \(Gemini が自動生成\)/);
  assert.match(joined, /q1\nq2/);
  assert.match(joined, /1\. A — https:\/\/a\.example/);
  assert.match(joined, /2\. B — https:\/\/b\.example/);
});

test("formatOutput: text が無いときは finishReason 付きの代替を出す", async () => {
  const logs = [];
  const j = { candidates: [{ finishReason: "SAFETY", content: { parts: [] } }] };
  await mod.formatOutput(j, { log: (s) => logs.push(s) });
  assert.match(logs[0], /回答テキストなし \/ finishReason: SAFETY/);
});

test("formatOutput: 検索クエリが空なら未接地警告とソースなしを出す", async () => {
  const logs = [];
  const j = { candidates: [{ content: { parts: [{ text: "X" }] } }] };
  await mod.formatOutput(j, { log: (s) => logs.push(s) });
  const joined = logs.join("\n");
  assert.match(joined, /未接地の回答かもしれません/);
  assert.match(joined, /\(なし\)/);
  assert.match(joined, /\(参照ソースなし\)/);
});

// ============================================================================
// 9. runMain end-to-end (in-process)
// ============================================================================

test("runMain: AI Studio 経路で fetch が generativelanguage を叩き、出力が log に出る", async () => {
  const fakeJson = {
    candidates: [{ content: { parts: [{ text: "main-answer" }] } }],
  };
  const stub = makeFetchStub(() => fetchResponse({ json: fakeJson }));
  const logs = [];
  await mod.runMain({
    argv: ["node", "search.js", "MyQuery"],
    env: { GEMINI_API_KEY: "K" },
    log: (s) => logs.push(s),
    opts: { fetch: stub },
  });
  assert.match(stub.records[0].url, /^https:\/\/generativelanguage\.googleapis\.com\//);
  assert.match(logs.join("\n"), /main-answer/);
});

test("runMain: Vertex AI 経路で OAuth → generateContent の順で fetch する", async () => {
  const { pem } = genTestRsa();
  const sa = { client_email: "svc@example", private_key: pem, project_id: "PR" };
  await withTmpFile(JSON.stringify(sa), async (tmp) => {
    const stub = makeFetchStub((url) => {
      if (url.includes("oauth2.googleapis.com")) {
        return fetchResponse({ json: { access_token: "TT" } });
      }
      return fetchResponse({ json: { candidates: [{ content: { parts: [{ text: "vertex-out" }] } }] } });
    });
    const logs = [];
    await mod.runMain({
      argv: ["node", "search.js", "q"],
      env: { GOOGLE_APPLICATION_CREDENTIALS: tmp, GEMINI_LOCATION: "us-central1", GEMINI_MODEL: "gemini-2.5-flash" },
      log: (s) => logs.push(s),
      opts: { fetch: stub },
    });
    assert.strictEqual(stub.records.length, 2);
    assert.match(stub.records[0].url, /oauth2\.googleapis\.com/);
    assert.match(
      stub.records[1].url,
      /^https:\/\/us-central1-aiplatform\.googleapis\.com\/v1\/projects\/PR\/locations\/us-central1\/publishers\/google\/models\/gemini-2\.5-flash:generateContent$/,
    );
    assert.match(logs.join("\n"), /vertex-out/);
  });
});

test("runMain: query 未指定なら GsearchError(1)", async () => {
  await assert.rejects(
    () => mod.runMain({ argv: ["node", "search.js"], env: { GEMINI_API_KEY: "K" } }),
    (e) => e instanceof mod.GsearchError && e.exitCode === 1 && /usage/.test(e.message),
  );
});

test("runMain: 両 env 未設定なら GsearchError(1)", async () => {
  await assert.rejects(
    () => mod.runMain({ argv: ["node", "search.js", "q"], env: {} }),
    (e) =>
      e instanceof mod.GsearchError &&
      e.exitCode === 1 &&
      /GEMINI_API_KEY/.test(e.message) &&
      /GOOGLE_APPLICATION_CREDENTIALS/.test(e.message),
  );
});
