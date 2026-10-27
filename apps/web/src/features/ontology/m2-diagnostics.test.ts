import { describe, expect, it } from "vitest";
import { diagnosticLocation } from "./semantic-status";
import type { AssessmentDiagnostic, OntologyDraft } from "../../lib/api/g2-generated";

const draft = {
  hashes: { ontologyHash: "o", shapesHash: "s", vocabularyHash: null, dataHash: "d", bundleHash: "b" },
  sources: { ontologyTurtle: "<urn:A> <urn:p> <urn:B> .", shapesTurtle: "# shape", vocabularyTurtle: null, dataTurtle: "" },
  projection: { nodes: [{ id: "urn:A" }] },
} as OntologyDraft;
const item: AssessmentDiagnostic = {
  sourceId: "ontology", sourceHash: "o", line: null, column: null,
  diagnostic: { code: "test", severity: "error", message: "测试", path: "urn:p",
    focusNode: { kind: "iri", value: "urn:A", datatype: null, language: null } },
};

describe("M2 诊断只能定位当前来源", () => {
  it("同源hash匹配才给源文档与确实存在的focus节点，未知行列不猜测", () => {
    expect(diagnosticLocation(item, draft, false)).toEqual({ field: "ontologyTurtle", focus: "urn:A", line: null, column: null });
  });
  it("过期hash或dirty拒绝定位", () => {
    expect(diagnosticLocation({ ...item, sourceHash: "old" }, draft, false)).toBeNull();
    expect(diagnosticLocation(item, draft, true)).toBeNull();
  });
  it("bundle不对应单源，未知sourceId及不存在focus不伪造节点", () => {
    expect(diagnosticLocation({ ...item, sourceId: "bundle", sourceHash: "b" }, draft, false)).toBeNull();
    expect(diagnosticLocation({ ...item, sourceId: "unknown" }, draft, false)).toBeNull();
    const diagnostic = { ...item.diagnostic, focusNode: { kind: "iri" as const, value: "urn:missing", datatype: null, language: null } };
    expect(diagnosticLocation({ ...item, diagnostic }, draft, false)?.focus).toBeNull();
  });
  it("blank sourceShape不产生原文位置，即使外层附带行列", () => {
    const blank = { ...item, sourceId: "shapes", sourceHash: "s", line: 1, column: 1,
      sourceShape: { kind: "blank" as const, value: "b0", datatype: null, language: null } };
    expect(diagnosticLocation(blank, draft, false)).toMatchObject({ field: "shapesTurtle", line: null, column: null });
  });
  it("只有服务器正整数且在当前源实际边界内才保留行列", () => {
    expect(diagnosticLocation({ ...item, line: 1, column: 2 }, draft, false)).toMatchObject({ line: 1, column: 2 });
    expect(diagnosticLocation({ ...item, line: 99, column: 2 }, draft, false)).toMatchObject({ line: null, column: null });
  });
});
