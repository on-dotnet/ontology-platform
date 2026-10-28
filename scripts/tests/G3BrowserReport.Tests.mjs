import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { writeBrowserEntryReport } from "../acceptance/browser-entry-report.mjs";

test("standalone entry preserves exact detailed Smoke fault and timing receipt", async () => {
  const root = await mkdtemp(join(tmpdir(), "ontology-smoke-evidence-"));
  const before = process.env.PLATFORM_EVIDENCE_DIR;
  process.env.PLATFORM_EVIDENCE_DIR = "docs/evidence/G3-M3-001/runtime/test";
  try {
    const directory = resolve(root, process.env.PLATFORM_EVIDENCE_DIR);
    await mkdir(directory, { recursive: true });
    const detailed = JSON.stringify({ status: "PASS", durationMs: 1234,
      fault: { expectedFailure: true, restoredOutcome: "PASS" } }) + "\n";
    await writeFile(join(directory, "workspace-smoke.json"), detailed);
    await writeBrowserEntryReport(root, "workspace-smoke", { status: "PASS", stage: "workspace-smoke" });
    assert.equal(await readFile(join(directory, "workspace-smoke.json"), "utf8"), detailed);
    assert.deepEqual(JSON.parse(await readFile(join(directory, "workspace-smoke-entry.json"), "utf8")),
      { status: "PASS", stage: "workspace-smoke" });
  } finally {
    if (before === undefined) delete process.env.PLATFORM_EVIDENCE_DIR;
    else process.env.PLATFORM_EVIDENCE_DIR = before;
    await rm(root, { recursive: true, force: true });
  }
});
