import type { OntologyDraft, SourceBundle } from "../../lib/api/g2-generated";
/** 源码本地缓冲与已确认修订分开，冲突不会替换用户文本。 */
export type DraftState = { draft: OntologyDraft; name: string; sources: SourceBundle };
/** 用服务器确认的完整源初始化缓冲。 */
export function draftState(draft: OntologyDraft): DraftState { return { draft, name: draft.name, sources: { ...draft.sources } }; }
/** 任一权威源或名称变化均标记未保存，图布局不在本状态中。 */
export function isDirty(state: DraftState) { return state.name !== state.draft.name || Object.keys(state.sources).some(key => state.sources[key as keyof SourceBundle] !== state.draft.sources[key as keyof SourceBundle]); }
/** 仅更新指定原始源，不在浏览器解析或重建OWL。 */
export function updateSource(state: DraftState, field: keyof SourceBundle, value: string): DraftState { return { ...state, sources: { ...state.sources, [field]: value } }; }
/** 默认拒绝覆盖dirty；只有明确丢弃或保存成功才应用远端修订。 */
export function receiveDraft(state: DraftState, draft: OntologyDraft, discard = false): DraftState { return isDirty(state) && !discard ? state : draftState(draft); }

/** 新建草稿也必须区分未提供术语源与已提供的空文件。 */
export function isNewDraftDirty(name: string, sources: SourceBundle): boolean {
  return name !== "" || sources.ontologyTurtle !== "" || sources.shapesTurtle !== ""
    || sources.dataTurtle !== "" || sources.vocabularyTurtle !== null;
}
