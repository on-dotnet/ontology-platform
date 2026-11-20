import assert from "node:assert/strict";
import { test } from "node:test";
process.env.OMQ_PRODUCT_RUN ??= "product-resume-01";
const omq = await import("../maintenance/workflow-oracle-query-fixture.mjs");
const issuer = "http://localhost:15743", realm = "/realms/g2-180e1435711f03fa";

function fixture(options = {}) {
  let time = 0, address = new URL(issuer + realm + "/protocol/openid-connect/auth"), handler, submitted = false;
  const events = [], frame = {}, user = {}, password = { get value() { assert.fail("password accessed"); } };
  const form = { action: options.action ?? issuer + realm + "/login-actions/authenticate", method: options.method ?? "post" };
  user.form = password.form = form;
  const button = { form: options.foreign ? {} : form, hasAttribute: name => name === options.override };
  const page = {
    url: () => address.href, mainFrame: () => frame, isClosed: () => options.closed ?? false,
    on: (name, fn) => { assert.equal(name,"request"); handler = fn; }, off: () => { handler = null; },
    bringToFront: async () => {
      events.push("front");
      if(options.immediate){submitted=true;handler({method:()=>"POST",url:()=>form.action,frame:()=>frame});}
    },
    locator: selector => ({ fill: async value => { assert.equal(selector,"#username"); user.value = options.wrongUser ?? value; },
      waitFor: async () => {}, isEnabled: async () => !options.disabled, focus: async () => events.push("focus") }),
    evaluate: async (fn, args) => {
      globalThis.location = address;
      globalThis.document = { querySelector: selector => selector === "#username" ? user : selector === "#password" ? password
        : selector === "#kc-login" ? button : options.rejected && submitted ? { textContent: "Invalid username or password." } : null };
      try { return fn(args); } finally { delete globalThis.location; delete globalThis.document; }
    },
  };
  const now = () => time;
  const wait = async ms => {
    time += ms;
    if (!submitted && time >= (options.submitAfter ?? 60000)) {
      submitted = true;
      handler?.({ method: () => "POST", url: () => form.action + "?session_code=NEVER_RECORDED", frame: () => frame,
        postData() { assert.fail("body accessed"); }, headers() { assert.fail("headers accessed"); } });
    }
    if (submitted && !options.noCallback && time >= (options.submitAfter ?? 60000) + 100)
      address = new URL("http://localhost:15741/api/v1/platform/me");
  };
  return { page, events, now, wait, advance: ms => { time += ms; }, options: { now, wait, onProgress: event => events.push(event) } };
}

test("human wait beyond old forty seconds succeeds and CSRF/me share remaining deadline", async () => {
  const f = fixture(); const lease = await omq.completeCurrentLogin(f.page,"viewer-a",f.options);
  assert(f.now() > 40000); assert(lease.remaining() <= 39900);
  f.advance(30000); assert(lease.remaining() <= 9900);
  f.advance(10000); assert.throws(lease.remaining,{ safeCode:"ORACLE_LOGIN_SUBMITTED_TIMEOUT" });
  assert.equal(f.events.find(e=>e.event==="FORM_INTERACTIVE").entry,"040700Z");
});

test("unsubmitted and submitted timeouts are distinct without origin guessing", async () => {
  for (const [options, code] of [[{submitAfter:Infinity},"ORACLE_LOGIN_WAITING_FOR_INPUT"],
      [{submitAfter:50000,noCallback:true},"ORACLE_LOGIN_SUBMITTED_TIMEOUT"]]) {
    const f=fixture(options);
    await assert.rejects(omq.completeCurrentLogin(f.page,"viewer-a",{...f.options,window:{durationMs:100000,deadline:null}}),error=>{
      assert.equal(error.safeCode,code); assert.equal(error.loginObservation.submitted,options.submitAfter!==Infinity);
      assert(!JSON.stringify(error.loginObservation).includes("session_code")); return true;
    });
  }
});

test("submission near batch end cannot obtain another forty seconds",async()=>{
  const f=fixture({submitAfter:599900,noCallback:true});
  await assert.rejects(omq.completeCurrentLogin(f.page,"viewer-a",f.options),{safeCode:"ORACLE_LOGIN_SUBMITTED_TIMEOUT"});
  assert.equal(f.now(),600000);
});

test("four accounts share one absolute human deadline",async()=>{
  const window={deadline:null,durationMs:600000};
  const f=fixture(); await omq.completeCurrentLogin(f.page,"viewer-a",{...f.options,window});
  assert.equal(window.deadline,600000);
  const g=fixture({submitAfter:Infinity}); g.advance(599900);
  await assert.rejects(omq.completeCurrentLogin(g.page,"operator-ab",{...g.options,window}),{safeCode:"ORACLE_LOGIN_WAITING_FOR_INPUT"});
  assert.equal(g.now(),600000);
});

for(const [name,options] of [["wrong action",{action:issuer+realm+"/other"}],["get form",{method:"get"}],
    ["foreign button",{foreign:true}],["override action",{override:"formaction"}],["override method",{override:"formmethod"}],
    ["wrong account",{wrongUser:"g2-operator-a"}]]) test(name,async()=>{
  const f=fixture(options);await assert.rejects(omq.completeCurrentLogin(f.page,"viewer-a",f.options),{safeCode:"ORACLE_LOGIN_FORM_MISMATCH"});
  assert.equal(f.events.length,0);
});

test("credential rejection and cancellation stop immediately",async()=>{
  const rejected=fixture({submitAfter:100,rejected:true,noCallback:true});
  await assert.rejects(omq.completeCurrentLogin(rejected.page,"viewer-a",rejected.options),{safeCode:"ORACLE_LOGIN_CREDENTIALS_REJECTED"});
  assert.equal(rejected.now(),100);
  const cancelled=fixture({closed:true});
  await assert.rejects(omq.completeCurrentLogin(cancelled.page,"viewer-a",cancelled.options),{safeCode:"ORACLE_LOGIN_CANCELLED"});
});

test("current identity projection and identified ticket failure classifications",()=>{
  const me={subjectId:omq.originalSubject("viewer-a"),roles:["platform.viewer"],scopes:[{organizationId:"org-demo",siteId:"site-a"}]};
  assert(omq.currentProjection("viewer-a",me));assert(!omq.currentProjection("operator-a",me));
  assert(!omq.currentProjection("viewer-a",{...me,scopes:[{organizationId:"other",siteId:"site-a"}]}));
  for(const kind of ["SUBJECT_MISMATCH","TTL_INSUFFICIENT","REVOKED","TICKET_UNAVAILABLE"])
    assert.equal(omq.sessionRejection("ValueError: ORACLE_ADMISSION_OMQ_SESSION_"+kind+"_"+"a".repeat(32)),"OMQ_SESSION_"+kind);
});

test("submission during foreground handoff retains forty-second deadline",async()=>{
  const f=fixture({immediate:true,submitAfter:50000});
  await assert.rejects(omq.completeCurrentLogin(f.page,"viewer-a",f.options),{safeCode:"ORACLE_LOGIN_SUBMITTED_TIMEOUT"});
  assert.equal(f.now(),40000);
});
