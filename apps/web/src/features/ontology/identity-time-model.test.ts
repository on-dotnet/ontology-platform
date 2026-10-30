import { describe, expect, it } from "vitest";
import type { RdfTerm, VocabularySnapshot, VocabularySourceTriple } from "../../lib/api/g2-generated";
import { rdfType } from "./structural-edit";
import { semantic, xsd } from "./vocabulary-model";
import { claimChanges, closeClaimChanges, eventChanges, identityDirectory, time, timestampTicks, type ClaimInput } from "./identity-time-model";

const iri = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const literal = (value: string): RdfTerm => ({ kind: "literal", value, datatype: null, language: null });
const row = (subject: string, predicate: string, object: RdfTerm, sourceId = "ontology"): VocabularySourceTriple =>
  ({ sourceId, triple: { subject: iri(subject), predicate, object } });
const snapshot = (triples: VocabularySourceTriple[] = []): VocabularySnapshot => ({ draftId: "draft-a", releaseId: null,
  manifestHash: null, revision: 2, hashes: { ontologyHash: "o", shapesHash: "s", vocabularyHash: "v", dataHash: "d", bundleHash: "b" },
  profileVersion: "4", profileHash: "profile4", triples: [row("urn:asset:a", rdfType, iri("http://www.w3.org/2002/07/owl#NamedIndividual")), ...triples], diagnostics: [] });
const input: ClaimInput = { iri: "urn:claim:new", siteId: "site-a", sourceNamespace: "synthetic.erp", externalIdentifier: "EQ-01",
  targetIri: "urn:asset:a", declarationSource: "urn:synthetic:source:v1", from: "2026-01-01T00:00:00Z", to: "" };
const scope = { organizationId: "org-a", siteIds: ["site-a", "site-b"] };
const stamp = (value: string): RdfTerm => ({ ...literal(value), datatype: xsd + "dateTimeStamp" });
const history = [row("urn:claim:old", rdfType, iri(semantic + "IdentityClaim")),
  row("urn:claim:old", semantic + "validityInterval", iri("urn:interval:old")),
  row("urn:interval:old", rdfType, iri(time + "Interval")), row("urn:interval:old", time + "hasBeginning", iri("urn:point:from")),
  row("urn:point:from", rdfType, iri(time + "Instant")), row("urn:point:from", time + "inXSDDateTimeStamp", stamp("2026-01-01T00:00:00Z"))];

describe("M4身份时间精确命令与历史保护", () => {
  it("组织和厂区来自资产范围，声明来源显式，未知终点不伪造无穷或sameAs", () => {
    const changes = claimChanges(snapshot(), scope, "vocabulary", input);
    expect(changes.find(item => item.edit.predicateIri === semantic + "organizationId")?.edit.newObject?.value).toBe("org-a");
    expect(changes.find(item => item.edit.predicateIri === semantic + "siteId")?.edit.newObject?.value).toBe("site-a");
    expect(changes.find(item => item.edit.predicateIri === semantic + "declarationSource")?.edit.newObject).toEqual(iri("urn:synthetic:source:v1"));
    expect(changes.some(item => item.edit.predicateIri === time + "hasEnd")).toBe(false);
    expect(changes.some(item => item.edit.predicateIri.endsWith("sameAs"))).toBe(false);
    expect(changes.every(item => item.sourceId === "vocabulary" && item.edit.oldObject === null)).toBe(true);
  });
  it("不能扩大厂区或把未登记目标当作已有身份", () => {
    expect(() => claimChanges(snapshot(), scope, "ontology", { ...input, siteId: "site-c" })).toThrow("当前资产范围");
    expect(() => claimChanges(snapshot(), scope, "ontology", { ...input, targetIri: "urn:asset:missing" })).toThrow("显式登记类型");
  });
  it("新声明与嵌套时间IRI不能覆盖任何已保存资源", () => {
    expect(() => claimChanges(snapshot([row("urn:claim:new/validity", rdfType, iri(time + "Interval"))]), scope, "ontology", input)).toThrow("IRI已被声明");
    expect(() => claimChanges(snapshot(), scope, "ontology", { ...input, from: "2026-03-01T00:00:00Z", to: "2026-02-01T00:00:00Z" })).toThrow("起点早于终点");
  });
  it("同编号不同厂区仍有独立IRI，目录不会合并", () => {
    const source = snapshot([row("urn:claim:a", rdfType, iri(semantic + "IdentityClaim")), row("urn:claim:a", semantic + "externalIdentifier", literal("EQ-01")),
      row("urn:claim:a", semantic + "siteId", literal("site-a")), row("urn:claim:b", rdfType, iri(semantic + "IdentityClaim")),
      row("urn:claim:b", semantic + "externalIdentifier", literal("EQ-01")), row("urn:claim:b", semantic + "siteId", literal("site-b"))]);
    expect(identityDirectory(source, "EQ-01").map(item => item.iri)).toEqual(["urn:claim:a", "urn:claim:b"]);
  });
  it("关闭历史只增补终点，完整保留身份和起点", () => {
    const changes = closeClaimChanges(snapshot(history), "urn:claim:old", "2026-02-01T00:00:00+08:00");
    expect(changes.map(item => item.edit.predicateIri)).toContain(time + "hasEnd");
    expect(changes.every(item => item.edit.oldObject === null)).toBe(true);
    expect(changes.some(item => item.edit.subjectIri === "urn:claim:old" || item.edit.subjectIri === "urn:point:from")).toBe(false);
  });
  it("旧终点只可收窄，精确旧RDF项和来源保留，禁止扩张", () => {
    const source = snapshot([...history, row("urn:interval:old", time + "hasEnd", iri("urn:point:to")),
      row("urn:point:to", rdfType, iri(time + "Instant"), "vocabulary"),
      row("urn:point:to", time + "inXSDDateTimeStamp", stamp("2026-03-01T00:00:00Z"), "vocabulary")]);
    const changes = closeClaimChanges(source, "urn:claim:old", "2026-02-01T00:00:00Z");
    expect(changes).toHaveLength(1);
    expect(changes[0].sourceId).toBe("vocabulary");
    expect(changes[0].edit.oldObject).toEqual(stamp("2026-03-01T00:00:00Z"));
    expect(() => closeClaimChanges(source, "urn:claim:old", "2026-04-01T00:00:00Z")).toThrow("不能扩张");
  });
  it("共享时间和跨源多值不挑第一个，也不隐式改变别的历史声明", () => {
    expect(() => closeClaimChanges(snapshot([...history, row("urn:claim:other", semantic + "validityInterval", iri("urn:interval:old"))]),
      "urn:claim:old", "2026-02-01T00:00:00Z")).toThrow("多个资源共享");
    expect(() => closeClaimChanges(snapshot([...history, row("urn:claim:old", semantic + "validityInterval", iri("urn:interval:other"), "vocabulary")]),
      "urn:claim:old", "2026-02-01T00:00:00Z")).toThrow("多值歧义");
  });
  it("事件不能与时间模板使用同一IRI，空观察时间只删除精确旧值", () => {
    expect(() => eventChanges(snapshot(), "ontology", { iri: "urn:event:a", timeIri: "urn:event:a", kind: "point",
      from: "2026-01-01T00:00:00Z", to: "", observed: "" })).toThrow("不同IRI");
    const source = snapshot([row("urn:event:a", rdfType, iri(semantic + "Event")),
      row("urn:event:a", time + "hasTime", iri("urn:time:old")),
      row("urn:event:a", semantic + "observedAtUtc", stamp("2026-01-03T00:00:00Z"), "vocabulary")]);
    const changes = eventChanges(source, "ontology", { iri: "urn:event:a", timeIri: "urn:time:new", kind: "point", from: "", to: "", observed: "" });
    expect(changes.find(item => item.edit.predicateIri === semantic + "observedAtUtc")).toMatchObject({ sourceId: "vocabulary",
      edit: { oldObject: stamp("2026-01-03T00:00:00Z"), newObject: null } });
    expect(changes.some(item => item.edit.predicateIri === time + "inXSDDateTimeStamp")).toBe(false);
  });
  it("更新事件只替换精确引用，新时间模板与独立观察时间完整提交，旧点不被改写", () => {
    const source = snapshot([row("urn:event:a", rdfType, iri(semantic + "Event")), row("urn:event:a", time + "hasTime", iri("urn:time:old"), "vocabulary")]);
    const changes = eventChanges(source, "ontology", { iri: "urn:event:a", timeIri: "urn:time:new", kind: "interval",
      from: "2026-01-01T00:00:00Z", to: "2026-01-02T00:00:00Z", observed: "2026-01-03T00:00:00Z" });
    expect(changes.find(item => item.edit.predicateIri === time + "hasTime")).toMatchObject({ sourceId: "vocabulary",
      edit: { oldObject: iri("urn:time:old"), newObject: iri("urn:time:new") } });
    expect(changes.some(item => item.edit.subjectIri === "urn:time:old")).toBe(false);
    expect(changes.find(item => item.edit.predicateIri === semantic + "observedAtUtc")?.edit.newObject).toEqual(stamp("2026-01-03T00:00:00Z"));
  });
});

describe("M4前端时间词法不猜机器时区", () => {
  it.each(["2026-01-01T00:00:00", "2026-02-30T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:00:60Z",
    "2026-01-01T00:00:00+14:01", "2026-01-01T00:00:00Z\n", "2026-01-01T00:00:00Z\t", "2026-01-01T00:00:00.12345678Z", "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])("拒绝非法词法 %s", value => {
    expect(timestampTicks(value)).toBeNull();
  });
  it("时区等价以同一时刻比较，七位精度不被毫秒截断", () => {
    expect(timestampTicks("2026-01-01T08:00:00+08:00")).toBe(timestampTicks("2026-01-01T00:00:00Z"));
    expect(timestampTicks("2026-01-01T00:00:00.0000002Z")! - timestampTicks("2026-01-01T00:00:00.0000001Z")!).toBe(1n);
    expect(timestampTicks("2024-02-29T00:00:00Z")).not.toBeNull();
  });
});
