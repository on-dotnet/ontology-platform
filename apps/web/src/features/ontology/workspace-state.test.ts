import { describe, expect, it } from "vitest";
import { initialWorkspaceView, workspaceView, editAvailability } from "./workspace-state";

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
