import { test } from "vitest";
import assert from "node:assert/strict";
import { displayQueryValue, decodeQueryResponse, displayQueryCandidate, bindQuerySessionBoundary } from "./g4-query-model";
import { createG4QueryClient } from "./g4-query-api";

test("leaving a query clears protected data and aborts late responses before identity revalidation", () => {
  const windowEvents = new EventTarget();
  const documentEvents = Object.assign(new EventTarget(), { visibilityState: "visible" });
  const request = new AbortController();
  let result: string | null = "actor-a-result";
  const transitions: string[] = [];
  const dispose = bindQuerySessionBoundary(windowEvents, documentEvents,
    () => { result = null; request.abort(); transitions.push("clear"); }, () => { assert.equal(result, null); transitions.push("verify"); });
  windowEvents.dispatchEvent(new Event("blur"));
  if (!request.signal.aborted) result = "late-actor-a-response";
  assert.equal(result, null);
  windowEvents.dispatchEvent(new Event("focus"));
  assert.deepEqual(transitions, ["clear", "clear", "verify"]);
  documentEvents.visibilityState = "hidden";
  documentEvents.dispatchEvent(new Event("visibilitychange"));
  assert.equal(transitions.at(-1), "clear");
  dispose();
  const count = transitions.length;
  windowEvents.dispatchEvent(new Event("focus"));
  assert.equal(transitions.length, count);
});

test("same-site candidates remain distinguishable even with identical labels and external ids", () => {
  const candidate = { entityIri: "urn:entity:one", entityTypeIris: ["urn:type:asset"], externalId: "asset-1", organizationId: "org-demo", siteId: "site-a", label: "设备", evidenceIds: ["e-1"] };
  assert.match(displayQueryCandidate(candidate), /asset-1/);
  assert.match(displayQueryCandidate(candidate), /site-a/);
  assert.notEqual(displayQueryCandidate(candidate), displayQueryCandidate({ ...candidate, entityIri: "urn:entity:two" }));
});

test("query values preserve decimal trailing zero, Int64 and source microseconds", () => {
  assert.equal(displayQueryValue({ type: "decimal", lexical: "9007199254740993.20", precision: 20, scale: 2 }), "9007199254740993.20");
  assert.equal(displayQueryValue({ type: "int64", lexical: "9223372036854775807" }), "9223372036854775807");
  assert.equal(displayQueryValue({ type: "timestampUtc", lexical: "2026-11-14T01:02:03.123456Z" }), "2026-11-14T01:02:03.123456Z");
  assert.equal(displayQueryValue({ type: "null", declaredType: "string", lexical: null }), "空值");
  assert.equal(displayQueryValue({ type: "string", lexical: "" }), "空字符串");
});

test("execution progress never becomes a seventh business status or fake EMPTY", () => {
  const running = { queryId: "query-1", executionStatus: "RUNNING", createdAtUtc: "2026-11-14T00:00:00.000000Z", completedAtUtc: null,
    expiresAtUtc: "2026-11-15T00:00:00.000000Z", resultHash: null, errorCode: null };
  assert.equal(decodeQueryResponse(running).kind, "execution");
  assert.throws(() => decodeQueryResponse({ ...running, executionStatus: "EMPTY" }));
  assert.throws(() => decodeQueryResponse({ ...running, schemaVersion: "g4.query-result.v1" }));
  assert.throws(() => decodeQueryResponse({ status: "EMPTY", data: [] }));
});

test("cancel uses CSRF POST without body and result recovery is a no-store GET", async () => {
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  const view = { queryId: "query-1", executionStatus: "CANCELLED", createdAtUtc: "2026-11-14T00:00:00.000000Z", completedAtUtc: "2026-11-14T00:00:01.000000Z",
    expiresAtUtc: "2026-11-15T00:00:00.000000Z", resultHash: null, errorCode: null };
  const fetcher: typeof fetch = async (input, init) => {
    const path = String(input); calls.push({ path, init });
    return new Response(JSON.stringify(path === "/auth/csrf" ? { requestToken: "synthetic-csrf" } : view), { headers: { "Content-Type": "application/json", "X-Query-Id": "query-1" } });
  };
  const client = createG4QueryClient(fetcher);
  await client.cancel("query-1");
  assert.equal(calls[1].init?.method, "POST");
  assert.equal(new Headers(calls[1].init?.headers).get("X-CSRF-TOKEN"), "synthetic-csrf");
  assert.equal(calls[1].init?.body, undefined);
  await client.result("query-1");
  assert.equal(calls[2].path, "/api/v1/data/semantic-queries/query-1/result");
  assert.equal(calls[2].init?.method, "GET");
  assert.equal(calls[2].init?.cache, "no-store");
  assert.equal(calls[2].init?.credentials, "same-origin");
});
