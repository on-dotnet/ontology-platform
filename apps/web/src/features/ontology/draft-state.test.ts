import { describe, expect, it } from "vitest";
import { draftState, isDirty, receiveDraft, updateSource } from "./draft-state";
import type { OntologyDraft } from "../../lib/api/g2-generated";
const draft = { draftId: "d", revision: 1, name: "合成", sources: { ontologyTurtle: "original", shapesTurtle: "", vocabularyTurtle: null, dataTurtle: "" } } as OntologyDraft;
describe("草稿状态", () => {
  it("dirty使投影过期，重新加载不覆盖本地文本", () => {
    const state = updateSource(draftState(draft), "ontologyTurtle", "local"); expect(isDirty(state)).toBe(true);
    expect(receiveDraft(state, { ...draft, revision: 2 }).sources.ontologyTurtle).toBe("local"); expect(state.draft.revision).toBe(1);
  });
  it("明确丢弃后加载新revision才清除dirty", () => {
    const state = updateSource(draftState(draft), "ontologyTurtle", "local");
    const remote = { ...draft, revision: 2, sources: { ...draft.sources, ontologyTurtle: "remote" } };
    expect(receiveDraft(state, remote, true).sources.ontologyTurtle).toBe("remote"); expect(isDirty(receiveDraft(state, remote, true))).toBe(false);
  });
});
