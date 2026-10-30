import { describe, expect, it } from "vitest";
import type { SourceHashes, VersionDiff } from "../../lib/api/g2-generated";
import { fixedVersion, lineEnding, sameVersion, sourceLineChanges, versionDiffMatches } from "./version-diff-model";

const hashes: SourceHashes = { ontologyHash: "a".repeat(64), shapesHash: "b".repeat(64), vocabularyHash: null, dataHash: "c".repeat(64), bundleHash: "d".repeat(64) };
const request = { from: { kind: "DRAFT" as const, id: "draft", revision: 1 }, to: { kind: "RELEASE" as const, id: "release-fixed", revision: null } };
const scope = { organizationId: "org", siteIds: ["site-a", "site-b"] };
function diff(): VersionDiff {
  return { assetId: "asset", scope, from: request.from, to: request.to, baseHashes: hashes, targetHashes: hashes,
    baseManifestHash: null, targetManifestHash: "f".repeat(64), sources: ["ontology", "shapes", "vocabulary", "data"].map((sourceId, index) => ({
      sourceId, baseText: index === 2 ? null : "", targetText: index === 2 ? null : "", baseHash: [hashes.ontologyHash, hashes.shapesHash, null, hashes.dataHash][index],
      targetHash: [hashes.ontologyHash, hashes.shapesHash, null, hashes.dataHash][index], sourceChanged: false, graph: { status: "EQUIVALENT", code: "equal", visitedNodes: 0, elapsedMilliseconds: 0 },
      baseTripleCount: 0, targetTripleCount: 0, addedTriples: [], removedTriples: [], tripleDeltaStatus: "EQUIVALENT",
    })) };
}

describe("M4固定版本选择与回复边界", () => {
  it("草稿必须固定正整数修订，Release永远显式revision=null", () => {
    expect(fixedVersion("DRAFT", "draft", "2")).toEqual({ kind: "DRAFT", id: "draft", revision: 2 });
    expect(fixedVersion("RELEASE", "release-fixed", "latest")).toEqual({ kind: "RELEASE", id: "release-fixed", revision: null });
  });
  it.each(["0", "-1", "latest", "1.5", "9007199254740993", "", " 2"])("拒绝未固定修订 %s", value => {
    expect(fixedVersion("DRAFT", "draft", value)).toBeNull();
  });
  it("同ID不同revision不是同一版本，版本类型不同也不相同", () => {
    expect(sameVersion(request.from, { ...request.from, revision: 2 })).toBe(false);
    expect(sameVersion(request.from, { kind: "RELEASE", id: "draft", revision: null })).toBe(false);
  });
  it("只接受固定请求、同资产完整scope与四个准确来源槽位", () => {
    expect(versionDiffMatches(diff(), request, "asset", { ...scope, siteIds: ["site-b", "site-a"] })).toBe(true);
    for (const changed of [
      { ...diff(), from: { ...request.from, revision: 2 } }, { ...diff(), assetId: "other" },
      { ...diff(), scope: { ...scope, siteIds: ["site-a"] } }, { ...diff(), sources: diff().sources.slice(1) },
      { ...diff(), sources: diff().sources.map((source, index) => index === 0 ? { ...source, sourceId: "data" } : source) },
      { ...diff(), sources: diff().sources.map((source, index) => index === 0 ? { ...source, baseHash: "forged" } : source) },
    ]) expect(versionDiffMatches(changed, request, "asset", scope)).toBe(false);
  });
  it("原型属性来源名、空字段和缺Graph均失败关闭", () => {
    const forged = { ...diff(), baseHashes: {}, targetHashes: {}, sources: ["__proto__", "constructor", "toString", "hasOwnProperty"]
      .map(sourceId => ({ sourceId, sourceChanged: false })) };
    expect(versionDiffMatches(forged, request, "asset", scope)).toBe(false);
    for (const property of ["graph", "baseText", "targetText", "baseHash", "addedTriples"]) {
      const broken = structuredClone(diff());
      delete (broken.sources[0] as unknown as Record<string, unknown>)[property];
      expect(versionDiffMatches(broken, request, "asset", scope)).toBe(false);
    }
  });
  it("manifest必须与DRAFT/RELEASE种类匹配，Release hash必须为准确格式", () => {
    expect(versionDiffMatches({ ...diff(), baseManifestHash: "f".repeat(64) }, request, "asset", scope)).toBe(false);
    expect(versionDiffMatches({ ...diff(), targetManifestHash: null }, request, "asset", scope)).toBe(false);
    expect(versionDiffMatches({ ...diff(), targetManifestHash: "manifest-fixed" }, request, "asset", scope)).toBe(false);
    expect(versionDiffMatches({ ...diff(), targetManifestHash: "f".repeat(64) + "\n" }, request, "asset", scope)).toBe(false);
    expect(versionDiffMatches({ ...diff(), from: { kind: "DRAFT", id: "draft", revision: null } }, request, "asset", scope)).toBe(false);
  });
  it("图状态和typed三元组字段缺失不能在展示时崩溃", () => {
    const value = diff();
    expect(versionDiffMatches({ ...value, sources: value.sources.map((source, index) => index ? source : { ...source, graph: {} }) },
      request, "asset", scope)).toBe(false);
    expect(versionDiffMatches({ ...value, sources: value.sources.map((source, index) => index ? source : { ...source, addedTriples: [{}] }) },
      request, "asset", scope)).toBe(false);
  });
  it("absent和空源不能混淆，声称sourceChanged不能替代原文对照", () => {
    const value = diff();
    value.sources[2] = { ...value.sources[2], targetText: "", targetHash: "e".repeat(64), sourceChanged: true };
    value.targetHashes = { ...hashes, vocabularyHash: "e".repeat(64) };
    expect(versionDiffMatches(value, request, "asset", scope)).toBe(true);
    value.sources[2].sourceChanged = false;
    expect(versionDiffMatches(value, request, "asset", scope)).toBe(false);
  });
});

describe("M4原始源码行对照保真", () => {
  it("替换中间行保留两侧行号、BOM、CRLF和尾部context", () => {
    const result = sourceLineChanges("\uFEFF# head\r\nold\n# tail\r", "\uFEFF# head\r\nnew\n# tail\r");
    expect(result).toEqual([
      { kind: "context", baseLine: 1, targetLine: 1, text: "\uFEFF# head\r\n" },
      { kind: "removed", baseLine: 2, targetLine: null, text: "old\n" },
      { kind: "added", baseLine: null, targetLine: 2, text: "new\n" },
      { kind: "context", baseLine: 3, targetLine: 3, text: "# tail\r" },
    ]);
    expect(lineEnding(result[0].text)).toBe("CRLF");
  });
  it("只改换行也明确字节变化，空行不能丢失", () => {
    const result = sourceLineChanges("a\r\n\r\n", "a\n\n");
    expect(result.filter(row => row.kind === "removed").map(row => row.text).join("")).toBe("a\r\n\r\n");
    expect(result.filter(row => row.kind === "added").map(row => row.text).join("")).toBe("a\n\n");
  });
  it("无变化只产生context，末尾没有换行不被伪造", () => {
    expect(sourceLineChanges("# no newline", "# no newline")).toEqual([
      { kind: "context", baseLine: 1, targetLine: 1, text: "# no newline" },
    ]);
    expect(lineEnding("# no newline")).toBe("无行结束符");
    expect(sourceLineChanges(null, "")).toEqual([]);
  });
});
