import { lstatSync } from "node:fs";
import { isAbsolute, relative, resolve, dirname } from "node:path";

/** 只选择当前任务证据目录；拒绝路径逃逸及符号链接，不读取私有运行时内容。 */
export function evidenceDirectory(root) {
  const allowed = resolve(root, "docs/evidence");
  const selected = resolve(root, process.env.PLATFORM_EVIDENCE_DIR ?? "docs/evidence/G2-THIN-SLICE-001/master");
  const within = relative(allowed, selected);
  if (within.startsWith("..") || isAbsolute(within)) throw new Error("evidence_boundary_invalid");
  for (let current = selected; current !== resolve(root); current = dirname(current)) {
    if (lstatSync(current, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error("evidence_symlink_invalid");
  }
  return selected;
}
