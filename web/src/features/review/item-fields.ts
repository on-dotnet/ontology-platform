import type { Datatype, Element, ElementKind, Synonym } from '@/features/ontologies/api';
import { DATATYPES, displayName, elementName, turtleSummary } from '@/features/ontologies/api';

import type { ChangeItem, ElementFields } from './api';

/** The fields a merge would apply: the reviewer's edits over the AI proposal. */
export function effectiveFields(item: Pick<ChangeItem, 'proposed' | 'edited'>): ElementFields {
  return { ...item.proposed, ...(item.edited ?? {}) };
}

/**
 * What the item shows: the target's current values (update, delete, restore) under the proposed
 * and edited ones, so references and names are known even when only one field changes.
 */
export function shownFields(item: Pick<ChangeItem, 'proposed' | 'edited' | 'before'>): ElementFields {
  return { ...(item.before ?? {}), ...effectiveFields(item) };
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
  return displayName(fields, language) || turtleSummary(fields.turtle) || undefined;
}

/** Name of what an element id or `temp_ref` points to, or undefined when it is unknown. */
export function refLabel(ref: string | null | undefined, context: RefContext): string | undefined {
  if (!ref) return undefined;
  const element = context.elementsById.get(ref);
  if (element) return elementName(element, context.language);
  const item = context.itemsByTempRef.get(ref);
  return item ? fieldsLabel(effectiveFields(item), context.language) : undefined;
}

/** Display name of an item: its proposed or current name; axioms are named by their Turtle. */
export function itemLabel(item: ChangeItem, context: RefContext): string {
  const own = fieldsLabel(shownFields(item), context.language);
  if (own) return own;
  const target = item.targetElementId ? context.elementsById.get(item.targetElementId) : undefined;
  return (target ? elementName(target, context.language) : '') || '—';
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
    .map((element) => ({ value: element.id, label: displayName(element, context.language), isNew: false }));
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

type EditableKind = Extract<ElementKind, 'entity_type' | 'relation_type' | 'property'>;
const EDITABLE_KINDS: readonly ElementKind[] = ['entity_type', 'relation_type', 'property'];

function isEditableKind(kind: ElementKind): kind is EditableKind {
  return EDITABLE_KINDS.includes(kind);
}

/**
 * Reviewers may edit creates and updates of types, relations and properties; other items are
 * decided as they are. So are elements with an IRI of their own (imported ones): their names
 * follow the file, not the naming rules this form checks. A create carries its IRI; an update's
 * target says whether it has one.
 */
export function isEditable(item: Pick<ChangeItem, 'kind' | 'op' | 'proposed' | 'edited' | 'targetElementId'>, context: RefContext): boolean {
  if (!isEditableKind(item.kind) || (item.op !== 'create' && item.op !== 'update')) return false;
  const target = item.targetElementId ? context.elementsById.get(item.targetElementId) : undefined;
  return !effectiveFields(item).iri && !target?.explicitIri;
}

/** Which fields the form shows: updates change descriptive fields only; names and references are fixed. */
export function editableFields(kind: ElementKind, op: ChangeItem['op']): EditField[] {
  if (!isEditableKind(kind) || (op !== 'create' && op !== 'update')) return [];
  const descriptive: EditField[] = ['labelZh', 'labelEn', 'definitionZh', 'definitionEn', 'synonymsZh', 'synonymsEn'];
  if (op === 'update') return descriptive;
  const byKind: Record<EditableKind, EditField[]> = {
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

// The descriptive fields an update may change, with the inputs each is edited in.
const UPDATE_INPUTS: readonly (readonly [keyof ElementFields, readonly EditField[]])[] = [
  ['labelZh', ['labelZh']],
  ['labelEn', ['labelEn']],
  ['definitionZh', ['definitionZh']],
  ['definitionEn', ['definitionEn']],
  ['synonyms', ['synonymsZh', 'synonymsEn']],
];

/**
 * The `edited` payload for the fields this kind and operation allow.
 *
 * An update carries only the fields that differ from `unedited` (the form for the proposal
 * without edits): a field left out keeps the element's current value, while one sent empty
 * would clear it.
 */
export function fromEditForm(kind: ElementKind, op: ChangeItem['op'], form: EditForm, unedited?: EditForm): ElementFields {
  const edited = allEditFields(kind, op, form);
  if (op !== 'update' || !unedited) return edited;
  const same = new Set(UPDATE_INPUTS.filter(([, inputs]) => inputs.every((input) => form[input] === unedited[input])).map(([key]) => key));
  return Object.fromEntries(Object.entries(edited).filter(([key]) => !same.has(key as keyof ElementFields)));
}

function allEditFields(kind: ElementKind, op: ChangeItem['op'], form: EditForm): ElementFields {
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

/** Fields compared in the before/after view of an update (rules and Turtle are shown whole instead). */
export const COMPARED_FIELDS = [
  'labelZh',
  'labelEn',
  'localName',
  'definitionZh',
  'definitionEn',
  'synonyms',
  'parentRef',
  'domainRef',
  'rangeRef',
  'inverseRef',
  'datatype',
  'unit',
  'required',
  'multiple',
  'autoShape',
] as const;
export type ComparedField = (typeof COMPARED_FIELDS)[number];

/** How compared values are written: list separator, names of references, datatypes and yes / no. */
export interface FieldFormat {
  separator: string;
  ref: (ref: string) => string;
  datatype: (datatype: string) => string;
  flag: (value: boolean) => string;
}

export function fieldText(fields: ElementFields | null | undefined, field: ComparedField, format: FieldFormat): string {
  if (!fields) return '';
  switch (field) {
    case 'synonyms':
      return (fields.synonyms ?? []).map((synonym) => synonym.text).join(format.separator);
    case 'parentRef':
    case 'domainRef':
    case 'rangeRef':
    case 'inverseRef': {
      const ref = fields[field];
      return ref ? format.ref(ref) : '';
    }
    case 'datatype':
      return fields.datatype ? format.datatype(fields.datatype) : '';
    case 'required':
    case 'multiple':
    case 'autoShape': {
      const value = fields[field];
      return value === null || value === undefined ? '' : format.flag(value);
    }
    default:
      return fields[field] ?? '';
  }
}
