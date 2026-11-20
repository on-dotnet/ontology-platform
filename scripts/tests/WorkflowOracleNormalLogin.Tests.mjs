import assert from "node:assert/strict";
import { test } from "node:test";

process.env.OMQ_PRODUCT_RUN ??= "product-resume-01";
const { completeCurrentLogin, currentProjection, loginOutcome, originalSubject, runId } = await import("../maintenance/workflow-oracle-query-fixture.mjs");

const issuer = "http://localhost:15743/realms/g2-180e1435711f03fa";
const login = issuer + "/protocol/openid-connect/auth";
const authenticate = issuer + "/login-actions/authenticate";
const callback = new URL("http://localhost:15741/api/v1/platform/me");
const marker = 'input#password[type="password"]:-webkit-autofill';

function fixture(options = {}) {
  const events = [];
  const input = {
    matches(selector) {
      assert.equal(selector, ":-webkit-autofill");
      return options.stillMarked ?? true;
    },
    get value() { assert.fail("Password value accessed"); },
  };
  const username = {};
  const submit = {
    hasAttribute(name) { return name === options.override; },
  };
  const form = {
    action: options.action ?? authenticate,
    method: options.method ?? "post",
    querySelector(selector) {
      if (selector === "#username") return username;
      assert.equal(selector, "#kc-login");
      return submit;
    },
    requestSubmit(button) {
      assert.equal(button, submit);
      events.push("nativeSubmit");
    },
  };
  input.form = form;
  submit.form = options.foreignSubmitter ? {} : form;
  const page = {
    url() { return options.initial ?? login; },
    async bringToFront() { events.push("foreground"); },
    locator(selector) {
      if (selector === "#username") return { async fill(value) {
        assert.equal(value, "g2-viewer-a");
        username.value = options.currentUser ?? value;
        events.push("publicUsername");
      } };
      if (selector === "#password") return { async focus() { events.push("focus"); } };
      assert.equal(selector, marker);
      return {
        async waitFor({ state, timeout }) {
          assert.equal(state, "visible"); assert.equal(timeout, 2000);
          if (!options.marked) throw Object.assign(new Error(), { name: "TimeoutError" });
        },
        async count() { return options.marked ? 1 : 0; },
        async evaluate(fn, expected, { timeout }) {
          assert(timeout > 0 && timeout <= 40000);
          globalThis.location = new URL(options.currentUrl ?? login);
          try { fn(input, expected); }
          finally { delete globalThis.location; }
        },
      };
    },
    async waitForFunction(classify, origins, { timeout }) {
      assert.equal(classify, loginOutcome);
      assert.equal(origins.api, callback.origin);
      assert(timeout > 0 && timeout <= 40000);
      events.push("awaitCallback");
      if (options.timeout) throw Object.assign(new Error(), { name: "TimeoutError" });
      return { jsonValue: async () => options.outcome ?? "CALLBACK" };
    },
  };
  return { page, events };
}

test("formal login reports bounded failure and verifies role and organization/site pairs", async () => {
  await assert.rejects(completeCurrentLogin(fixture({ timeout: true }).page, "viewer-a"), { safeCode: "ORACLE_LOGIN_WAITING_FOR_INPUT" });
  for (const outcome of ["ORACLE_LOGIN_CREDENTIALS_REJECTED", "ORACLE_LOGIN_CALLBACK_ERROR"])
    await assert.rejects(completeCurrentLogin(fixture({ outcome }).page, "viewer-a"), { safeCode: outcome });
  const me = { subjectId: originalSubject("viewer-a"), roles: ["platform.viewer"], scopes: [{ organizationId: "org-demo", siteId: "site-a" }] };
  assert(currentProjection("viewer-a", me));
  assert(!currentProjection("operator-a", me));
  assert(!currentProjection("viewer-a", { ...me, roles: ["platform.operator"] }));
  assert(!currentProjection("viewer-a", { ...me, scopes: [{ organizationId: "other", siteId: "site-a" }] }));
});

test("the registered browser predicate distinguishes issuer errors and the exact callback", () => {
  const origins = { issuer: new URL(issuer).origin, api: callback.origin, realm: new URL(issuer).pathname };
  try {
    globalThis.location = new URL(login);
    globalThis.document = { querySelector: () => null };
    assert.equal(loginOutcome(origins), false);
    globalThis.document.querySelector = () => ({ textContent: "Invalid username or password." });
    assert.equal(loginOutcome(origins), "ORACLE_LOGIN_CREDENTIALS_REJECTED");
    globalThis.location = new URL("/signin-oidc?error=access_denied", callback);
    assert.equal(loginOutcome(origins), "ORACLE_LOGIN_CALLBACK_ERROR");
    globalThis.location = callback;
    assert.equal(loginOutcome(origins), "CALLBACK");
  } finally { delete globalThis.location; delete globalThis.document; }
});

test("approved public identity and realm", async () => {
  assert.equal(runId, "product-resume-01");
  assert.match(originalSubject("viewer-a"), /^[a-f0-9-]{36}$/);
  const wrong = fixture({ initial: "http://localhost:15743/realms/other/auth" });
  await assert.rejects(completeCurrentLogin(wrong.page, "viewer-a"), /ORACLE_RESTORED_REALM/);
  await assert.rejects(completeCurrentLogin(wrong.page, "other"), /ORACLE_OIDC_SUBJECT/);
  assert.deepEqual(wrong.events, []);
});

for (const [name, options, submitCount] of [
  ["missing autofill marker", {}, 0],
  ["different current account", { marked: true, currentUser: "g2-operator-a" }, 0],
  ["wrong form action", { marked: true, action: issuer + "/other" }, 0],
  ["wrong form method", { marked: true, method: "get" }, 0],
  ["button action override", { marked: true, override: "formaction" }, 0],
  ["button method override", { marked: true, override: "formmethod" }, 0],
  ["button owned by another form", { marked: true, foreignSubmitter: true }, 0],
  ["current realm changed", { marked: true, currentUrl: "http://localhost:15743/realms/other/auth" }, 0],
  ["marker disappeared", { marked: true, stillMarked: false }, 0],
  ["matching marked form", { marked: true }, 1],
]) {
  test(name, async () => {
    const { page, events } = fixture(options);
    await completeCurrentLogin(page, "viewer-a");
    assert.deepEqual(events.slice(0, 3), ["publicUsername", "foreground", "focus"]);
    assert.equal(events.filter(event => event === "nativeSubmit").length, submitCount);
    assert.equal(events.at(-1), "awaitCallback");
  });
}
