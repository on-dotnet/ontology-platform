/** 直接执行真实M5短分支的身份/参数/清理控制流；不冒充OIDC或浏览器产品验收。 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../acceptance/g2-live-browser.mjs", import.meta.url), "utf8");
const start = source.indexOf("  } else if (process.argv.includes('--m5-api-only')");
const end = source.indexOf("  } else if (process.argv.includes('--m4-impact-only'))", start);
assert.ok(start > 0 && end > start, "真实M5分支缺失");
const body = source.slice(source.indexOf("{", start) + 1, end)
  .replace(/const \{ runM5Checks \} = await import\('\.\/g3-m5-browser\.mjs'\);/, "");
const execute = new (Object.getPrototypeOf(async function () {}).constructor)(
  "process", "identity", "runM5Checks", "root", "origin", "operator", "check", "command", `let phase;${body}`);

for (const flag of ["--m5-api-only", "--m5-ui-only"]) {
  for (const fail of [false, true]) test(`真实分支 ${flag} 故障=${fail}`, async () => {
    const opened = [], closed = [];
    const user = name => ({ name, context: { close: async () => closed.push(name) } });
    let received;
    const action = execute({ argv: [flag] }, async name => { opened.push(name); return user(name); }, async options => {
      received = options;
      assert.equal(options.viewer.name, "viewer-ab");
      assert.equal(options.single.name, "viewer-a");
      if (fail) throw new Error("synthetic_control_failure");
    }, "fixture", "http://localhost", user("operator"), () => {}, () => {});
    if (fail) await assert.rejects(action, /synthetic_control_failure/); else await action;
    assert.deepEqual(opened, ["viewer-ab", "viewer-a"]);
    assert.deepEqual(closed.sort(), ["operator", "viewer-a", "viewer-ab"].sort());
    assert.equal(received.apiOnly, flag === "--m5-api-only");
  });
}
