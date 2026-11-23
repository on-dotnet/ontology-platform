import type { Datatype, Element, ElementKind, Synonym } from '@/features/ontologies/api';
import { DATATYPES, elementLabel } from '@/features/ontologies/api';

import type { ChangeItem, ElementFields } from './api';

/** The fields a merge would apply: the reviewer's edits over the AI proposal. */
export function effectiveFields(item: Pick<ChangeItem, 'proposed' | 'edited'>): ElementFields {
  return { ...item.proposed, ...(item.edited ?? {}) };
}

/** Resolves element ids and `temp_ref`s of this change set to display names. */
export interface RefContext {
  elementsById: ReadonlyMap<string, Element>;
  itemsByTempRef: ReadonlyMap<string, ChangeItem>;
  language: string;
}

export function buildRefContext(items: readonly ChangeItem[], elements: readonly Element[], language: string): RefContext {
  return {
    elementsById: new Map(elements.map((element) => [element.id, element])),
    itemsByTempRef: new Map(items.filter((item) => item.tempRef).map((item) => [item.tempRef ?? '', item])),
    language,
  };
}

function fieldsLabel(fields: ElementFields, language: string): string | undefined {
  if (language.startsWith('en') && fields.labelEn) return fields.labelEn;
  return fields.labelZh ?? undefined;
}

/** Name of what an element id or `temp_ref` points to, or undefined when it is unknown. */
export function refLabel(ref: string | null | undefined, context: RefContext): string | undefined {
  if (!ref) return undefined;
  const element = context.elementsById.get(ref);
  if (element) return elementLabel(element, context.language);
  const item = context.itemsByTempRef.get(ref);
  return item ? fieldsLabel(effectiveFields(item), context.language) : undefined;
}

/** Display name of an item: its proposed label, or the target element's for updates without one. */
export function itemLabel(item: ChangeItem, context: RefContext): string {
  const own = fieldsLabel(effectiveFields(item), context.language);
  if (own) return own;
  const target = item.targetElementId ? context.elementsById.get(item.targetElementId) : undefined;
  if (target) return elementLabel(target, context.language);
  return (item.before ? fieldsLabel(item.before, context.language) : undefined) ?? '—';
}

export interface RefOption {
  value: string;
  label: string;
  /** Proposed by this change set rather than already in the ontology. */
  isNew: boolean;
}

/** Object types an item may point to: existing ones plus the non-rejected new ones in this change set. */
export function entityTypeOptions(items: readonly ChangeItem[], context: RefContext, excludeRef?: string | null): RefOption[] {
  const existing = [...context.elementsById.values()]
    .filter((element) => element.kind === 'entity_type' && element.status === 'active')
    .map((element) => ({ value: element.id, label: elementLabel(element, context.language), isNew: false }));
  const proposed = items
    .filter((item) => item.op === 'create' && item.kind === 'entity_type' && item.tempRef && item.decision !== 'rejected')
    .map((item) => ({ value: item.tempRef ?? '', label: fieldsLabel(effectiveFields(item), context.language) ?? '—', isNew: true }));
  return [...existing, ...proposed].filter((option) => option.value !== excludeRef);
}

// ---------- edit form ----------

export interface EditForm {
  localName: string;
  labelZh: string;
  labelEn: string;
  definitionZh: string;
  definitionEn: string;
  synonymsZh: string;
  synonymsEn: string;
  parentRef: string;
  domainRef: string;
  rangeRef: string;
  datatype: string;
  unit: string;
  required: boolean;
  multiple: boolean;
}

export type EditField = keyof EditForm;
/** i18n keys of field errors, by field. */
export type EditErrors = Partial<Record<EditField, string>>;

const SYNONYM_SEPARATOR = /[,，、;；\n]+/;
const PASCAL_CASE = /^[A-Z][A-Za-z0-9]*$/;
const CAMEL_CASE = /^[a-z][A-Za-z0-9]*$/;

function synonymsText(synonyms: readonly Synonym[] | null | undefined, lang: Synonym['lang'], separator: string): string {
  return (synonyms ?? [])
    .filter((synonym) => synonym.lang === lang)
    .map((synonym) => synonym.text)
    .join(separator);
}

function parseSynonyms(text: string, lang: Synonym['lang']): Synonym[] {
  return text
    .split(SYNONYM_SEPARATOR)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => ({ lang, text: part }));
}

/** Form values for the fields; `separator` joins synonyms for display (any common separator is accepted back). */
export function toEditForm(fields: ElementFields, separator: string): EditForm {
  return {
    localName: fields.localName ?? '',
    labelZh: fields.labelZh ?? '',
    labelEn: fields.labelEn ?? '',
    definitionZh: fields.definitionZh ?? '',
    definitionEn: fields.definitionEn ?? '',
    synonymsZh: synonymsText(fields.synonyms, 'zh', separator),
    synonymsEn: synonymsText(fields.synonyms, 'en', separator),
    parentRef: fields.parentRef ?? '',
    domainRef: fields.domainRef ?? '',
    rangeRef: fields.rangeRef ?? '',
    datatype: fields.datatype ?? '',
    unit: fields.unit ?? '',
    required: fields.required ?? false,
    multiple: fields.multiple ?? false,
  };
}

/** Which fields the form shows: updates change descriptive fields only; names and references are fixed. */
export function editableFields(kind: ElementKind, op: ChangeItem['op']): EditField[] {
  const descriptive: EditField[] = ['labelZh', 'labelEn', 'definitionZh', 'definitionEn', 'synonymsZh', 'synonymsEn'];
  if (op === 'update') return descriptive;
  const byKind: Record<ElementKind, EditField[]> = {
    entity_type: ['parentRef'],
    relation_type: ['domainRef', 'rangeRef', 'required', 'multiple'],
    property: ['domainRef', 'datatype', 'unit', 'required', 'multiple'],
  };
  return ['localName', ...descriptive, ...byKind[kind]];
}

export function validateEdit(kind: ElementKind, op: ChangeItem['op'], form: EditForm, selfRef: string | null): EditErrors {
  const fields = new Set(editableFields(kind, op));
  const errors: EditErrors = {};
  if (!form.labelZh.trim()) errors.labelZh = 'review.edit.errors.labelZhRequired';
  if (fields.has('localName')) {
    const name = form.localName.trim();
    const pattern = kind === 'entity_type' ? PASCAL_CASE : CAMEL_CASE;
    if (!name) errors.localName = 'review.edit.errors.localNameRequired';
    else if (!pattern.test(name)) errors.localName = kind === 'entity_type' ? 'review.edit.errors.localNamePascal' : 'review.edit.errors.localNameCamel';
  }
  if (fields.has('parentRef') && selfRef && form.parentRef === selfRef) errors.parentRef = 'review.edit.errors.parentSelf';
  if (fields.has('domainRef') && !form.domainRef) errors.domainRef = 'review.edit.errors.domainRequired';
  if (fields.has('rangeRef') && !form.rangeRef) errors.rangeRef = 'review.edit.errors.rangeRequired';
  if (fields.has('datatype') && !(DATATYPES as readonly string[]).includes(form.datatype)) {
    errors.datatype = 'review.edit.errors.datatypeRequired';
  }
  return errors;
}

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

/** The `edited` payload for the fields this kind and operation allow. */
export function fromEditForm(kind: ElementKind, op: ChangeItem['op'], form: EditForm): ElementFields {
  const fields = new Set(editableFields(kind, op));
  const edited: ElementFields = {
    labelZh: form.labelZh.trim(),
    labelEn: textOrNull(form.labelEn),
    definitionZh: textOrNull(form.definitionZh),
    definitionEn: textOrNull(form.definitionEn),
    synonyms: [...parseSynonyms(form.synonymsZh, 'zh'), ...parseSynonyms(form.synonymsEn, 'en')],
  };
  if (fields.has('localName')) edited.localName = form.localName.trim();
  if (fields.has('parentRef')) edited.parentRef = form.parentRef || null;
  if (fields.has('domainRef')) edited.domainRef = form.domainRef || null;
  if (fields.has('rangeRef')) edited.rangeRef = form.rangeRef || null;
  if (fields.has('datatype')) edited.datatype = (form.datatype || null) as Datatype | null;
  if (fields.has('unit')) edited.unit = textOrNull(form.unit);
  if (fields.has('required')) edited.required = form.required;
  if (fields.has('multiple')) edited.multiple = form.multiple;
  return edited;
}

/** Fields compared in the before/after view of an update. */
export const COMPARED_FIELDS = ['labelZh', 'labelEn', 'definitionZh', 'definitionEn', 'synonyms'] as const;
export type ComparedField = (typeof COMPARED_FIELDS)[number];

export function fieldText(fields: ElementFields | null | undefined, field: ComparedField, separator: string): string {
  if (!fields) return '';
  if (field === 'synonyms') return (fields.synonyms ?? []).map((synonym) => synonym.text).join(separator);
  return fields[field] ?? '';
}
