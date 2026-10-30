import { describe, expect, it } from "vitest";
import { initialWorkspaceView, workspaceView, editAvailability, structuralWriteGate } from "./workspace-state";

describe("E0-B 工作区状态合同", () => {
  it("初始源码；打开和新建均恢复源码并选择源码面板", () => {
    expect(initialWorkspaceView.centerView).toBe("source");
    const graph = workspaceView({ ...initialWorkspaceView, selected: "urn:a" }, { type: "view", view: "graph" });
    for (const type of ["open", "new"] as const) {
      expect(workspaceView(graph, { type })).toEqual({ centerView: "source", panel: "source", selected: "" });
    }
  });
  it("graph→source保留选中IRI，窄屏面板显式切换不改变视图", () => {
    let state = workspaceView(initialWorkspaceView, { type: "select", iri: "urn:synthetic:m3:K" });
    state = workspaceView(state, { type: "view", view: "graph" });
    expect(state.centerView).toBe("graph");
    state = workspaceView(state, { type: "panel", panel: "inspect" });
    expect(state.panel).toBe("inspect");
    state = workspaceView(state, { type: "view", view: "source" });
    expect(state.selected).toBe("urn:synthetic:m3:K");
  });
  it("只读、忙碌、dirty及错误状态阻断结构编辑并提供确定原因", () => {
    expect(editAvailability({ canEdit: false, busy: false, dirty: false, failed: false })).toBe("当前身份仅可读取");
    expect(editAvailability({ canEdit: true, busy: true, dirty: false, failed: false })).toBe("命令正在执行");
    expect(editAvailability({ canEdit: true, busy: false, dirty: true, failed: false })).toBe("请先保存或丢弃未保存源码");
    expect(editAvailability({ canEdit: true, busy: false, dirty: false, failed: true })).toBe("词汇快照读取失败，请刷新");
    expect(editAvailability({ canEdit: true, busy: false, dirty: false, failed: false })).toBeNull();
  });
});


describe("M4未提交身份时间不能被结构写入静默替换", () => {
  const ready = { canEdit: true, busy: false, dirty: false, structuralPending: false,
    reason: "显式结构修改", hasBasicCapability: true };
  it.each(["身份时间表单", "身份时间批次", "词汇批次"])("%s未提交时，显示和执行均阻断且原内容保留", pendingKind => {
    const buffered = { kind: pendingKind, claimIri: "urn:synthetic:claim:keep", externalIdentifier: "KEEP-01" };
    const before = structuredClone(buffered);
    let revision = 7, writes = 0;
    const gate = structuralWriteGate({ ...ready, structuralPending: true });
    expect(gate.blocked).toContain("当前内容已保留");
    const rejected = gate.submit(() => {
      writes++; revision++;
      buffered.claimIri = ""; buffered.externalIdentifier = "";
    });
    expect(rejected).toBe(gate.blocked);
    expect(writes).toBe(0);
    expect(revision).toBe(7);
    expect(buffered).toEqual(before);
  });
  it("源码脏缓冲同样拒绝实际写入回调", () => {
    let writes = 0;
    const gate = structuralWriteGate({ ...ready, dirty: true });
    expect(gate.submit(() => { writes++; })).toContain("未保存源码");
    expect(writes).toBe(0);
  });
  it("只有显式提交或取消其它编辑后，新的门禁才放行一次结构命令", () => {
    let writes = 0;
    expect(structuralWriteGate({ ...ready, structuralPending: true }).submit(() => { writes++; })).not.toBeNull();
    const afterCancel = structuralWriteGate(ready);
    expect(afterCancel.blocked).toBeNull();
    expect(afterCancel.submit(() => { writes++; })).toBeNull();
    expect(writes).toBe(1);
  });
  it("权限、执行中、空理由和未知能力都不能因调用回调而绕过", () => {
    for (const status of [{ ...ready, canEdit: false }, { ...ready, busy: true },
      { ...ready, reason: " " }, { ...ready, hasBasicCapability: false }]) {
      let writes = 0;
      const gate = structuralWriteGate(status);
      expect(gate.blocked).not.toBeNull();
      expect(gate.submit(() => { writes++; })).not.toBeNull();
      expect(writes).toBe(0);
    }
  });
});
