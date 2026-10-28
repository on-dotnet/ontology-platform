import { describe, expect, it } from "vitest";
import type { OntologyDraft, VocabularySnapshot, VocabularySourceTriple } from "../../lib/api/g2-generated";
import { vocabularyDirectory, vocabularyChange, snapshotMatches, releaseProfile, predicates, semantic, skos } from "./vocabulary-model";
const iri = (value: string) => ({ kind: "iri" as const, value, datatype: null, language: null });
const literal = (value: string, language: string | null = null) => ({ kind: "literal" as const, value, datatype: null, language });
const row = (subject: string, predicate: string, object: ReturnType<typeof iri> | ReturnType<typeof literal>, sourceId = "vocabulary"): VocabularySourceTriple =>
  ({ sourceId, triple: { subject: iri(subject), predicate, object } });
const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: "v", dataHash: "d", bundleHash: "b" };
const snapshot: VocabularySnapshot = { draftId: "draft", releaseId: null, manifestHash: null, revision: 2, hashes, profileVersion: "3", profileHash: "p", diagnostics: [], triples: [] };

describe("M3 四源词汇视图与精确编辑", () => {
  it("目录搜索中文、英文和notation保留同名不同IRI及多源事实", () => {
    const triples = [row("urn:a", skos + "prefLabel", literal("温度", "zh")), row("urn:a", skos + "altLabel", literal("Temperature", "en"), "ontology"),
      row("urn:b", skos + "prefLabel", literal("温度", "zh")), row("urn:b", skos + "notation", literal("TEMP"))];
    expect(vocabularyDirectory({ ...snapshot, triples }, "温度").map(item => item.iri)).toEqual(["urn:a", "urn:b"]);
    expect(vocabularyDirectory({ ...snapshot, triples }, "temperature")[0].iri).toBe("urn:a");
    expect(vocabularyDirectory({ ...snapshot, triples }, "TEMP")).toHaveLength(2);
  });
  it("替换保留精确source及语言/datatype旧对象，不允许shapes/data结构写入", () => {
    const entry = row("urn:a", skos + "prefLabel", literal("温度", "ZH"), "ontology");
    const change = vocabularyChange(entry, literal("气温", "zh"));
    expect(change?.sourceId).toBe("ontology");
    expect(change?.edit.oldObject?.language).toBe("ZH");
    expect(change?.edit.newObject?.value).toBe("气温");
    expect(vocabularyChange({ ...entry, sourceId: "data" }, null)).toBeNull();
    expect(vocabularyChange({ ...entry, triple: { ...entry.triple, subject: { ...iri("b0"), kind: "blank" } } }, null)).toBeNull();
  });
  it("同bundle但任一源hash、草稿、revision不符均拒绝旧快照", () => {
    const draft = { draftId: "draft", revision: 2, hashes } as OntologyDraft;
    expect(snapshotMatches(snapshot, draft)).toBe(true);
    expect(snapshotMatches({ ...snapshot, hashes: { ...hashes, ontologyHash: "changed" } }, draft)).toBe(false);
    expect(snapshotMatches({ ...snapshot, revision: 1 }, draft)).toBe(false);
    expect(snapshotMatches({ ...snapshot, draftId: "other" }, draft)).toBe(false);
  });
  it("历史profile不填当前版本；七维指数和单位来源字段完整可选", () => {
    expect(releaseProfile({ ...snapshot, profileVersion: null, profileHash: null })).toBe("LEGACY_G2 / UNKNOWN");
    expect(releaseProfile(snapshot)).toContain("3");
    for (const key of ["lengthExponent", "massExponent", "timeExponent", "electricCurrentExponent", "temperatureExponent", "amountExponent", "luminousIntensityExponent", "quantityKind", "dimension", "nominalUnit", "canonicalUnit", "precision", "version", "standardSource", "symbol"])
      expect(predicates.some(item => item.iri === semantic + key)).toBe(true);
  });
});
