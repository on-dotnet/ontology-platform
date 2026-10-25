import { readFile, readdir, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
/** 仅将本轮批准的合成测试身份放入子进程，不写秘密文件或打印原始输出。 */
async function run() {
  const webRoot = resolve(import.meta.dirname, "..");
  const probe = process.argv.includes("--privacy-probe");
  const childEnvironment = { ...process.env, PLAYWRIGHT_NO_COPY_PROMPT: "1" };
  delete childEnvironment.DEBUG;
  delete childEnvironment.PWDEBUG;
  if (probe) {
    childEnvironment.PLATFORM_OIDC_PRIVACY_PROBE = "1";
  } else {
    const runtime = JSON.parse(await readFile(process.env.PLATFORM_TEST_RUNTIME, "utf8"));
    const realm = JSON.parse(await readFile(runtime.realmFile, "utf8"));
    for (const [username, variable] of [["wave2-viewer-a", "WAVE2_VIEWER_PASSWORD"], ["wave2-no-role-a", "WAVE2_NO_ROLE_PASSWORD"]]) {
      const value = realm.identities?.[username]?.password;
      if (!value) throw new Error("runtime_identity_missing");
      childEnvironment[variable] = value;
    }
  }
  const outputDirectory = resolve(webRoot, "artifacts/test-results/oidc");
  await rm(outputDirectory, { recursive: true, force: true });
  const child = spawn(process.execPath, ["../../.tools/pnpm/package/bin/pnpm.cjs", "--config.verifyDepsBeforeRun=false", "exec", "playwright", "test", "--config", "playwright.oidc.config.ts"], { cwd: webRoot, env: childEnvironment, stdio: ["ignore", "pipe", "pipe"] });
  let buffer = "";
  child.stdout.on("data", chunk => { buffer += chunk.toString(); });
  child.stderr.on("data", () => { /* 原始stderr可能含敏感调用参数，直接丢弃。 */ });
  const code = await new Promise((complete, reject) => { child.on("error", reject); child.on("close", complete); });
  const forbiddenArtifacts = (await readdir(outputDirectory, { recursive: true }).catch(() => [])).filter(path => /error-context|\.zip$|\.webm$|\.har$/.test(path));
  if (forbiddenArtifacts.length) {
    await rm(outputDirectory, { recursive: true, force: true });
    throw new Error("privacy_artifact_blocked");
  }
  const safeLines = buffer.split("\n").filter(line => line.startsWith("OIDC_SAFE "));
  if (safeLines.filter(line => JSON.parse(line.slice(10)).event === "test").length !== 2) throw new Error("test_reports_missing");
  for (const line of safeLines) process.stdout.write(line + "\n");
  process.stdout.write(`OIDC_SAFE ${JSON.stringify({ event: "privacy", status: "no-sensitive-artifacts", exitCode: code })}\n`);
  process.exitCode = code ?? 1;
}
run().catch(() => { process.stdout.write('OIDC_SAFE {"event":"setup","status":"failed","details":"withheld"}\n'); process.exitCode = 1; });
