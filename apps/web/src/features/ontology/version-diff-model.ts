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
const sourceSlots = new Map<string, keyof SourceHashes>([
  ["ontology", "ontologyHash"], ["shapes", "shapesHash"], ["vocabulary", "vocabularyHash"], ["data", "dataHash"],
]);
const hashPattern = /^[0-9a-f]{64}$/;
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const fields = (value: Record<string, unknown>, names: string[]) => names.every(name => Object.hasOwn(value, name));
const hash = (value: unknown): value is string => typeof value === "string" && value.length === 64 && hashPattern.test(value);
function hashes(value: unknown): value is SourceHashes {
  return record(value) && fields(value, ["ontologyHash", "shapesHash", "vocabularyHash", "dataHash", "bundleHash"])
    && [value.ontologyHash, value.shapesHash, value.dataHash, value.bundleHash].every(hash)
    && (value.vocabularyHash === null || hash(value.vocabularyHash));
}
function version(value: unknown): value is VersionRef {
  return record(value) && fields(value, ["kind", "id", "revision"]) && typeof value.id === "string" && value.id.trim() !== ""
    && (value.kind === "DRAFT" ? Number.isSafeInteger(value.revision) && (value.revision as number) > 0
      : value.kind === "RELEASE" && value.revision === null);
}
function scopeValid(value: unknown): value is ResourceScope {
  return record(value) && fields(value, ["organizationId", "siteIds"]) && typeof value.organizationId === "string"
    && value.organizationId.trim() !== "" && Array.isArray(value.siteIds) && value.siteIds.length > 0
    && value.siteIds.every(site => typeof site === "string" && site.trim() !== "") && new Set(value.siteIds).size === value.siteIds.length;
}
function graphValid(value: unknown): boolean {
  return record(value) && fields(value, ["status", "code", "visitedNodes", "elapsedMilliseconds"])
    && ["EQUIVALENT", "DIFFERENT", "INDETERMINATE"].includes(value.status as string)
    && typeof value.code === "string" && value.code.trim() !== "" && Number.isSafeInteger(value.visitedNodes)
    && (value.visitedNodes as number) >= 0 && typeof value.elapsedMilliseconds === "number"
    && Number.isFinite(value.elapsedMilliseconds) && value.elapsedMilliseconds >= 0;
}
function termValid(value: unknown, subject: boolean): boolean {
  return record(value) && fields(value, ["kind", "value", "datatype", "language"]) && typeof value.value === "string"
    && (subject ? value.kind === "iri" : value.kind === "iri" || value.kind === "literal")
    && (value.kind !== "iri" || value.value.trim() !== "")
    && (value.datatype === null || typeof value.datatype === "string") && (value.language === null || typeof value.language === "string");
}
function triplesValid(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.every(triple => record(triple) && fields(triple, ["subject", "predicate", "object"])
    && termValid(triple.subject, true) && typeof triple.predicate === "string" && triple.predicate.trim() !== "" && termValid(triple.object, false));
}

/** 拒绝错版本、跨范围、缺源和槽位hash错配的回复；实际字节真实性仍由服务器核验。 */
export function versionDiffMatches(value: unknown, request: CompareVersionsRequest, assetId: string, scope: ResourceScope): value is VersionDiff {
  if (!record(value) || !fields(value, ["from", "to", "assetId", "scope", "baseHashes", "targetHashes", "baseManifestHash", "targetManifestHash", "sources"])
    || !version(value.from) || !version(value.to) || !scopeValid(value.scope) || !hashes(value.baseHashes) || !hashes(value.targetHashes)
    || !sameVersion(value.from, request.from) || !sameVersion(value.to, request.to) || value.assetId !== assetId || !sameScope(value.scope, scope)) return false;
  if (value.from.kind === "DRAFT" ? value.baseManifestHash !== null : !hash(value.baseManifestHash)) return false;
  if (value.to.kind === "DRAFT" ? value.targetManifestHash !== null : !hash(value.targetManifestHash)) return false;
  const baseHashes = value.baseHashes, targetHashes = value.targetHashes;
  if (!Array.isArray(value.sources) || value.sources.length !== 4) return false;
  const sources = value.sources;
  if (new Set(sources.map(source => record(source) ? source.sourceId : undefined)).size !== 4) return false;
  return sources.every(source => {
    if (!record(source) || !fields(source, ["sourceId", "baseText", "targetText", "baseHash", "targetHash", "sourceChanged", "graph",
      "baseTripleCount", "targetTripleCount", "addedTriples", "removedTriples", "tripleDeltaStatus"]) || typeof source.sourceId !== "string") return false;
    const key = sourceSlots.get(source.sourceId);
    if (!key || !graphValid(source.graph) || !triplesValid(source.addedTriples) || !triplesValid(source.removedTriples)
      || !["EXACT", "EQUIVALENT", "INDETERMINATE"].includes(source.tripleDeltaStatus as string)) return false;
    const countValid = (count: unknown) => count === null || Number.isSafeInteger(count) && (count as number) >= 0;
    if (!countValid(source.baseTripleCount) || !countValid(source.targetTripleCount)) return false;
    if (source.sourceId !== "vocabulary" && (typeof source.baseText !== "string" || typeof source.targetText !== "string")) return false;
    return (source.baseText === null || typeof source.baseText === "string") && (source.targetText === null || typeof source.targetText === "string")
      && source.baseHash === baseHashes[key] && source.targetHash === targetHashes[key]
      && (source.baseText === null) === (source.baseHash === null) && (source.targetText === null) === (source.targetHash === null)
      && typeof source.sourceChanged === "boolean" && source.sourceChanged === (source.baseText !== source.targetText);
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
  const key = sourceSlots.get(sourceId);
  return key ? hashes[key] : null;
}
