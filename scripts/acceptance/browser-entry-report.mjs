import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { evidenceDirectory } from "./evidence-paths.mjs";

/** 外层入口回执与Smoke详细故障/恢复证据分文件保存。 */
export async function writeBrowserEntryReport(root, checkpoint, report) {
  const name = checkpoint === "workspace-smoke" ? "workspace-smoke-entry" : checkpoint;
  await writeFile(resolve(evidenceDirectory(root), name + ".json"), JSON.stringify(report, null, 2) + "\n");
}
