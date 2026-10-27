import { describe, expect, it } from "vitest";
import { preserveEditorSource } from "./source-bytes";
import { assessmentEligibility, comparisonLabel } from "./semantic-status";
import type { OntologyDraft, SemanticAssessment, SemanticSupportProfile } from "../../lib/api/g2-generated";

const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: null, dataHash: "d", bundleHash: "b" };
const draft = { draftId: "draft", revision: 3, hashes } as OntologyDraft;
const profile = { version: "1", hash: "profile", reasoningMode: "ASSERTED_ONLY" } as SemanticSupportProfile;
const now = Date.parse("2026-10-27T03:00:00Z");
const assessment: SemanticAssessment = {
  assessmentId: "assessment", validationReportId: "report", draftId: "draft", revision: 3, hashes,
  profileVersion: "1", profileHash: "profile", assessmentHash: "assessment-hash",
  assessedAtUtc: "2026-10-27T02:00:00Z", expiresAtUtc: "2026-10-28T02:00:00Z", executorVersion: "1",
  stages: ["PARSE", "SUPPORT", "SHACL_CORE", "GOVERNANCE"].map(name => ({ name, status: "PASS", code: "complete" })),
  publishEligible: true, diagnostics: [], budgetStatus: "COMPLETE",
};

describe("M1 字节与不确定性边界", () => {
  it("textarea仅规范化换行时保持BOM、混合换行、非BMP原始字节", () => {
    const original = "\uFEFF# 🏭\r\n<urn:a> <urn:b> <urn:c> .\r# end\n";
    expect(preserveEditorSource(original, original.replace(/\r\n?/g, "\n"))).toBe(original);
  });
  it("真实源码修改保留用户输入，不把新内容当no-op", () => {
    expect(preserveEditorSource("# old\r\n", "# new\n")).toBe("# new\n");
  });
  it("缺少assessment或profile明确UNKNOWN而非通过", () => {
    expect(assessmentEligibility(null, draft, profile, false, now)).toMatch(/UNKNOWN/);
    expect(assessmentEligibility(assessment, draft, null, false, now)).toMatch(/UNKNOWN/);
  });
  it("服务器eligible且全部绑定、必需阶段与预算有效才可提交", () => {
    expect(assessmentEligibility(assessment, draft, profile, false, now)).toBe("ELIGIBLE");
  });
  it.each([
    { revision: 2 }, { draftId: "other" }, { hashes: { ...hashes, dataHash: "changed" } },
    { profileHash: "old" }, { profileVersion: "2" }, { expiresAtUtc: "invalid" },
    { expiresAtUtc: "2026-10-27T01:00:00Z" }, { publishEligible: false },
    { budgetStatus: "INDETERMINATE" }, { stages: [] },
    { stages: [{ name: "PARSE", status: "INDETERMINATE" as const, code: "timeout" }] },
  ])("旧绑定、未知阶段、预算及过期均禁止提交 %j", patch => {
    expect(assessmentEligibility({ ...assessment, ...patch }, draft, profile, false, now)).not.toBe("ELIGIBLE");
  });
  it("任何额外未确定阶段都不能被已有PASS阶段掩盖", () => {
    const stages = [...assessment.stages, { name: "UNRECOGNIZED", status: "INDETERMINATE" as const, code: "unknown" }];
    expect(assessmentEligibility({ ...assessment, stages }, draft, profile, false, now)).not.toBe("ELIGIBLE");
  });
  it("重复必需阶段有失败时不显示资格通过", () => {
    const stages = [...assessment.stages, { name: "PARSE", status: "FAIL" as const, code: "failed" }];
    expect(assessmentEligibility({ ...assessment, stages }, draft, profile, false, now)).not.toBe("ELIGIBLE");
  });
  it("dirty源不沿用已保存修订的资格", () => {
    expect(assessmentEligibility(assessment, draft, profile, true, now)).not.toBe("ELIGIBLE");
  });
  it("OWL推理NOT_RUN在asserted-only下显式保留", () => {
    const stages = [...assessment.stages, { name: "OWL_REASONING", status: "NOT_RUN" as const, code: "asserted_only" }];
    expect(assessmentEligibility({ ...assessment, stages }, draft, profile, false, now)).toBe("ELIGIBLE");
  });
  it("预算耗尽不能被表述为零差异", () => {
    expect(comparisonLabel("INDETERMINATE")).toMatch(/未确定/);
    expect(comparisonLabel("UNRECOGNIZED")).toMatch(/UNKNOWN/);
    expect(comparisonLabel("EQUIVALENT")).toMatch(/等价/);
  });
});
