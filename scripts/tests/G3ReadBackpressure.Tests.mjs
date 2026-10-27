import { createServer } from "node:http";
import { test } from "node:test";
import assert from "node:assert/strict";
import { postSemanticRead } from "../acceptance/g3-read-backpressure.mjs";

/** 真实回环HTTP响应验证客户端协议；不把此测试冒充真实Jena业务验收。 */
async function exercise(responses, path = "/api/v1/semantic/queries") {
  let count = 0;
  const attempts = [];
  const server = createServer((request, response) => {
    const value = responses[Math.min(count++, responses.length - 1)];
    response.writeHead(value.status, { "Content-Type": "application/problem+json" });
    response.end(value.raw ?? JSON.stringify(value.body));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const api = { post: async (url, options) => {
      const response = await fetch(url, { method: "POST", body: JSON.stringify(options.data) });
      return { status: () => response.status, json: () => response.clone().json() };
    } };
    const response = await postSemanticRead(api, "http://127.0.0.1:" + server.address().port + path,
      { data: { synthetic: true } }, attempt => attempts.push(attempt));
    return { status: response.status(), count, attempts };
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test("real semantic_busy response waits and reissues only the read", async () => {
  const result = await exercise([{ status: 429, body: { code: "semantic_busy" } }, { status: 200, body: {} }]);
  assert.equal(result.status, 200);
  assert.equal(result.count, 2);
  assert.deepEqual(result.attempts.map(item => item.status), [429, 200]);
  assert.equal(result.attempts[0].code, "semantic_busy");
  assert.equal(result.attempts[0].waitMs, 250);
  assert.equal(result.attempts[1].waitMs, 0);
});

test("semantic_busy exhaustion stays failed with five recorded attempts", async () => {
  const result = await exercise([{ status: 429, body: { code: "semantic_busy" } }]);
  assert.equal(result.status, 429);
  assert.equal(result.count, 5);
  assert.deepEqual(result.attempts.map(item => item.waitMs), [250, 500, 1000, 2000, 0]);
});

test("a write is never retried even with the same busy code", async () => {
  const result = await exercise([{ status: 429, body: { code: "semantic_busy" } }], "/api/v1/release-activations");
  assert.equal(result.count, 1);
  assert.equal(result.status, 429);
});

test("unknown 429 code is not retried or echoed", async () => {
  const result = await exercise([{ status: 429, body: { code: "synthetic_unknown" } }]);
  assert.equal(result.count, 1);
  assert.equal(result.status, 429);
  assert.ok(result.attempts.every(item => item.code !== "synthetic_unknown"));
});

test("malformed 429 body is not retried", async () => {
  const result = await exercise([{ status: 429, raw: "{" }]);
  assert.equal(result.count, 1);
  assert.equal(result.status, 429);
});

test("non-busy service failure is not retried", async () => {
  const result = await exercise([{ status: 503, body: { code: "semantic_busy" } }]);
  assert.equal(result.count, 1);
  assert.equal(result.status, 503);
});
