import type { FullResult, Reporter, TestCase, TestResult } from "@playwright/test/reporter";
/** 只报告固定测试标识与状态，不输出异常、调用日志、URL或附加文件。 */
export default class SafeOidcReporter implements Reporter {
  onTestEnd(test: TestCase, result: TestResult) {
    const caseId = test.title.includes("无角色") ? "no-role" : "viewer";
    const step = test.annotations.filter(item => item.type === "safe-step").at(-1)?.description ?? "setup";
    const resourceStatus = test.annotations.find(item => item.type === "safe-resource-status")?.description;
    const legacyTarget = test.annotations.find(item => item.type === "safe-target")?.description;
    process.stdout.write(`OIDC_SAFE ${JSON.stringify({ event: "test", caseId, status: result.status, step, durationMs: result.duration, resourceStatus, legacyTarget })}\n`);
  }
  onError() { process.stdout.write('OIDC_SAFE {"event":"runner-error","status":"failed"}\n'); }
  onEnd(result: FullResult) { process.stdout.write(`OIDC_SAFE ${JSON.stringify({ event: "end", status: result.status })}\n`); }
}
