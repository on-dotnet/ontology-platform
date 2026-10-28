/** 三栏导航与选中实体的显式合同；打开资产和新建总是恢复源码。 */
export type WorkspaceView = { centerView: "source" | "graph"; panel: string; selected: string };
type ViewAction = { type: "open" | "new" } | { type: "view"; view: WorkspaceView["centerView"] }
  | { type: "panel"; panel: string } | { type: "select"; iri: string };
export const initialWorkspaceView: WorkspaceView = { centerView: "source", panel: "catalog", selected: "" };

/** 视图切换保留IRI，资产切换清空旧资产选择。 */
export function workspaceView(state: WorkspaceView, action: ViewAction): WorkspaceView {
  switch (action.type) {
    case "open": case "new": return { centerView: "source", panel: "source", selected: "" };
    case "view": return { ...state, centerView: action.view };
    case "panel": return { ...state, panel: action.panel };
    case "select": return { ...state, selected: action.iri };
  }
}

/** 结构写入的可见阻断原因；服务端仍是最终权限和CAS裁决者。 */
export function editAvailability(status: { canEdit: boolean; busy: boolean; dirty: boolean; failed: boolean }): string | null {
  if (!status.canEdit) return "当前身份仅可读取";
  if (status.busy) return "命令正在执行";
  if (status.dirty) return "请先保存或丢弃未保存源码";
  if (status.failed) return "词汇快照读取失败，请刷新";
  return null;
}
