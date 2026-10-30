import type { CompareVersionsRequest, ResourceScope, SourceHashes, VersionDiff, VersionRef, VersionRefKind } from "../../lib/api/g2-generated";

/** 用户必须选择固定修订，正式Release不能附带可变草稿修订。 */
export function fixedVersion(kind: VersionRefKind, id: string, revision: string): VersionRef | null {
  if (!id.trim()) return null;
  if (kind === "RELEASE") return { kind, id: id.trim(), revision: null };
  if (kind !== "DRAFT" || !/^[0-9]+$/.test(revision)) return null;
  const value = Number(revision);
  return Number.isSafeInteger(value) && value > 0 ? { kind, id: id.trim(), revision: value } : null;
}

/** 比较完整固定定位，不把同ID的不同草稿修订当作同一版本。 */
export function sameVersion(left: VersionRef, right: VersionRef) {
  return left.kind === right.kind && left.id === right.id && left.revision === right.revision;
}
export function sameScope(left: ResourceScope, right: ResourceScope) {
  return left.organizationId === right.organizationId && left.siteIds.length === right.siteIds.length
    && [...left.siteIds].sort().every((site, index) => site === [...right.siteIds].sort()[index]);
}
const sourceSlots = { ontology: "ontologyHash", shapes: "shapesHash", vocabulary: "vocabularyHash", data: "dataHash" } as const;

/** 拒绝错版本、跨范围、缺源和槽位hash错配的回复；实际字节真实性仍由服务器核验。 */
export function versionDiffMatches(diff: VersionDiff, request: CompareVersionsRequest, assetId: string, scope: ResourceScope): boolean {
  if (!sameVersion(diff.from, request.from) || !sameVersion(diff.to, request.to) || diff.assetId !== assetId || !sameScope(diff.scope, scope)) return false;
  if (diff.sources.length !== 4 || new Set(diff.sources.map(source => source.sourceId)).size !== 4) return false;
  return diff.sources.every(source => {
    const key = sourceSlots[source.sourceId as keyof typeof sourceSlots];
    return key && source.baseHash === diff.baseHashes[key] && source.targetHash === diff.targetHashes[key]
      && (source.baseText === null) === (source.baseHash === null) && (source.targetText === null) === (source.targetHash === null)
      && source.sourceChanged === (source.baseText !== source.targetText);
  });
}

/** 展示用行差异保留每行原始BOM和换行字节词法，不声称最小编辑距离。 */
export type SourceLineChange = { kind: "context" | "removed" | "added"; baseLine: number | null; targetLine: number | null; text: string };
const lines = (value: string) => value === "" ? [] : (value.match(/[^\r\n]*(?:\r\n|\r|\n|$)/g) ?? []).filter(value => value !== "");

/** 线性前后文对照避免浏览器做无界LCS；完整两侧原文仍可查看和导出。 */
export function sourceLineChanges(baseText: string | null, targetText: string | null): SourceLineChange[] {
  const base = lines(baseText ?? ""), target = lines(targetText ?? "");
  let prefix = 0, suffix = 0;
  while (prefix < base.length && prefix < target.length && base[prefix] === target[prefix]) prefix++;
  while (suffix < base.length - prefix && suffix < target.length - prefix
    && base[base.length - suffix - 1] === target[target.length - suffix - 1]) suffix++;
  return [
    ...base.slice(0, prefix).map((text, index) => ({ kind: "context" as const, baseLine: index + 1, targetLine: index + 1, text })),
    ...base.slice(prefix, base.length - suffix).map((text, index) => ({ kind: "removed" as const, baseLine: prefix + index + 1, targetLine: null, text })),
    ...target.slice(prefix, target.length - suffix).map((text, index) => ({ kind: "added" as const, baseLine: null, targetLine: prefix + index + 1, text })),
    ...base.slice(base.length - suffix).map((text, index) => ({ kind: "context" as const,
      baseLine: base.length - suffix + index + 1, targetLine: target.length - suffix + index + 1, text })),
  ];
}

/** 原始行结束符显式可见；BOM显示标记不会反写任何权威源。 */
export function lineEnding(text: string) {
  return text.endsWith("\r\n") ? "CRLF" : text.endsWith("\r") ? "CR" : text.endsWith("\n") ? "LF" : "无行结束符";
}
export function sourceHash(hashes: SourceHashes, sourceId: string): string | null {
  const key = sourceSlots[sourceId as keyof typeof sourceSlots];
  return key ? hashes[key] : null;
}
