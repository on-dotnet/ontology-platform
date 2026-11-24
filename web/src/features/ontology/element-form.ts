import {
  DATATYPES,
  type ConstraintRule,
  type ConstraintRuleFields,
  type Datatype,
  type Element,
  type ElementFields,
  type ElementKind,
  type LangText,
  type RdfValue,
  type Synonym,
} from '@/features/ontologies/api';

/** The kinds made and changed with the element form; axioms are edited as Turtle (expert mode). */
export type FormKind = Extract<ElementKind, 'entity_type' | 'relation_type' | 'property' | 'constraint'>;
export const FORM_KINDS: readonly FormKind[] = ['entity_type', 'relation_type', 'property', 'constraint'];

export function isFormKind(kind: ElementKind): kind is FormKind {
  return (FORM_KINDS as readonly ElementKind[]).includes(kind);
}

/** One rule of a constraint as typed into the form. */
export interface RuleForm {
  /** Stable React key; never sent. */
  key: string;
  pathRef: string;
  classRef: string;
  minCount: string;
  maxCount: string;
  datatype: string;
  /** Allowed values, one per line. */
  allowedValues: string;
  minValue: string;
  minExclusive: boolean;
  maxValue: string;
  maxExclusive: boolean;
  minLength: string;
  maxLength: string;
  pattern: string;
  flags: string;
  messageZh: string;
  messageEn: string;
  /**
   * The stored rule this one was read from. It keeps what the form does not edit (node kind,
   * messages in other languages) and the exact spelling of values the user left alone, so an
   * unchanged rule is saved exactly as it was.
   */
  source: ConstraintRule | null;
}

export type RuleField = Exclude<keyof RuleForm, 'key' | 'source'>;

export interface ElementForm {
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
  inverseRef: string;
  datatype: string;
  unit: string;
  required: boolean;
  multiple: boolean;
  rules: RuleForm[];
}

export type FormField = Exclude<keyof ElementForm, 'rules'>;

/** Error key of a rule's field. */
export function ruleErrorKey(rule: Pick<RuleForm, 'key'>, field: RuleField): string {
  return `rule:${rule.key}:${field}`;
}

/** i18n keys of field errors, by form field or `ruleErrorKey`. */
export type FormErrors = Record<string, string>;

const SYNONYM_SEPARATOR = /[,，、;；\n]+/;
const PASCAL_CASE = /^[A-Z][A-Za-z0-9]*$/;
const CAMEL_CASE = /^[a-z][A-Za-z0-9]*$/;
const NON_NEGATIVE_INTEGER = /^\d+$/;
const INTEGER = /^[+-]?\d+$/;
const DECIMAL = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;
// XPath regular expression flags SHACL accepts for sh:flags.
const PATTERN_FLAGS = /^[smixq]*$/;
const IRI_LIKE = /^(https?|urn):\S+$/i;
export const LOCAL_NAME_MAX = 128;

/** Object types and constraints use PascalCase local names; relations and properties camelCase. */
export function usesPascalCase(kind: FormKind): boolean {
  return kind === 'entity_type' || kind === 'constraint';
}

/**
 * Local name suggested from the English name: its letters and digits as PascalCase (object types,
 * constraints) or camelCase (relations, properties), starting with a letter. Empty when the
 * English name has no usable letters.
 */
export function suggestLocalName(english: string, kind: FormKind): string {
  const words = english
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean);
  const joined = words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join('');
  const name = joined.replace(/^[0-9]+/, '');
  if (!name) return '';
  if (usesPascalCase(kind)) return name.slice(0, LOCAL_NAME_MAX);
  // An acronym first ("CO2 content") reads better all lower case: co2Content, not cO2Content.
  const first = words.find((word) => /[A-Za-z]/.test(word.charAt(0))) ?? '';
  const camel =
    first && first === first.toUpperCase() && name.startsWith(first)
      ? first.toLowerCase() + name.slice(first.length)
      : name.charAt(0).toLowerCase() + name.slice(1);
  return camel.slice(0, LOCAL_NAME_MAX);
}

// ---------- reading ----------

let ruleKeys = 0;
function nextRuleKey(): string {
  ruleKeys += 1;
  return `rule-${ruleKeys}`;
}

function synonymsText(synonyms: readonly Synonym[], lang: Synonym['lang'], separator: string): string {
  return synonyms
    .filter((synonym) => synonym.lang === lang)
    .map((synonym) => synonym.text)
    .join(separator);
}

/** How a value is written in the form: an IRI in full, a literal as written with its language. */
export function valueText(value: RdfValue): string {
  if (value.iri) return value.iri;
  const text = value.lexical ?? '';
  return value.lang ? `${text}@${value.lang}` : text;
}

function numberText(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

// The message slots the form edits: Chinese (or, without one, the message without a language) and English.
function messageSlots(messages: readonly LangText[]): { zh: number; en: number } {
  const lang = (message: LangText) => (message.lang ?? '').toLowerCase();
  let zh = messages.findIndex((message) => lang(message).startsWith('zh'));
  if (zh < 0) zh = messages.findIndex((message) => !message.lang);
  const en = messages.findIndex((message) => lang(message).startsWith('en'));
  return { zh, en };
}

export function emptyRule(): RuleForm {
  return {
    key: nextRuleKey(),
    pathRef: '',
    classRef: '',
    minCount: '',
    maxCount: '',
    datatype: '',
    allowedValues: '',
    minValue: '',
    minExclusive: false,
    maxValue: '',
    maxExclusive: false,
    minLength: '',
    maxLength: '',
    pattern: '',
    flags: '',
    messageZh: '',
    messageEn: '',
    source: null,
  };
}

export function ruleToForm(rule: ConstraintRule): RuleForm {
  const messages = rule.message ?? [];
  const slots = messageSlots(messages);
  const min = rule.minInclusive ?? rule.minExclusive;
  const max = rule.maxInclusive ?? rule.maxExclusive;
  return {
    key: nextRuleKey(),
    pathRef: rule.pathId,
    classRef: rule.classId ?? '',
    minCount: numberText(rule.minCount),
    maxCount: numberText(rule.maxCount),
    datatype: rule.datatype ?? '',
    allowedValues: (rule.allowedValues ?? []).map(valueText).join('\n'),
    minValue: min ? valueText(min) : '',
    minExclusive: !rule.minInclusive && Boolean(rule.minExclusive),
    maxValue: max ? valueText(max) : '',
    maxExclusive: !rule.maxInclusive && Boolean(rule.maxExclusive),
    minLength: numberText(rule.minLength),
    maxLength: numberText(rule.maxLength),
    pattern: rule.pattern ?? '',
    flags: rule.flags ?? '',
    messageZh: messages[slots.zh]?.text ?? '',
    messageEn: messages[slots.en]?.text ?? '',
    source: rule,
  };
}

/** Form values of an element, or of a new element of `kind` (a constraint starts with one rule). */
export function toElementForm(element: Element | undefined, kind: FormKind, separator: string): ElementForm {
  if (!element) {
    return {
      localName: '',
      labelZh: '',
      labelEn: '',
      definitionZh: '',
      definitionEn: '',
      synonymsZh: '',
      synonymsEn: '',
      parentRef: '',
      domainRef: '',
      rangeRef: '',
      inverseRef: '',
      datatype: '',
      unit: '',
      required: false,
      multiple: false,
      rules: kind === 'constraint' ? [emptyRule()] : [],
    };
  }
  return {
    localName: element.localName ?? '',
    labelZh: element.labelZh ?? '',
    labelEn: element.labelEn ?? '',
    definitionZh: element.definitionZh ?? '',
    definitionEn: element.definitionEn ?? '',
    synonymsZh: synonymsText(element.synonyms, 'zh', separator),
    synonymsEn: synonymsText(element.synonyms, 'en', separator),
    parentRef: element.parentId ?? '',
    domainRef: element.domainId ?? '',
    rangeRef: element.rangeId ?? '',
    inverseRef: element.inverseId ?? '',
    datatype: element.datatype ?? '',
    unit: element.unit ?? '',
    required: element.required,
    multiple: element.multiple,
    rules: (element.rules ?? []).map(ruleToForm),
  };
}

// ---------- which fields, which are required ----------

const NAME_FIELDS: readonly FormField[] = ['labelZh', 'labelEn', 'localName', 'definitionZh', 'definitionEn'];
const SYNONYM_FIELDS: readonly FormField[] = ['synonymsZh', 'synonymsEn'];
const KIND_FIELDS: Record<FormKind, readonly FormField[]> = {
  entity_type: [...NAME_FIELDS, ...SYNONYM_FIELDS, 'parentRef'],
  relation_type: [...NAME_FIELDS, ...SYNONYM_FIELDS, 'domainRef', 'rangeRef', 'inverseRef', 'required', 'multiple'],
  property: [...NAME_FIELDS, ...SYNONYM_FIELDS, 'domainRef', 'datatype', 'unit', 'required', 'multiple'],
  // A constraint's names label the SHACL shape; synonyms do not apply to a shape.
  constraint: [...NAME_FIELDS, 'domainRef'],
};

export function formFields(kind: FormKind): ReadonlySet<FormField> {
  return new Set(KIND_FIELDS[kind]);
}

export interface FormMode {
  kind: FormKind;
  /** True when creating; an update cannot change the local name. */
  creating: boolean;
  /**
   * The element came with an IRI of its own (an import): like the server, the form does not
   * require a Chinese name, references or a datatype OWL does not require. A constraint always
   * needs its target type.
   */
  imported: boolean;
}

export function isRequired(field: FormField, mode: FormMode): boolean {
  switch (field) {
    case 'labelZh':
      return !mode.imported;
    case 'localName':
      return mode.creating;
    case 'domainRef':
      return mode.kind === 'constraint' || !mode.imported;
    case 'rangeRef':
      return mode.kind === 'relation_type' && !mode.imported;
    case 'datatype':
      return mode.kind === 'property' && !mode.imported;
    default:
      return false;
  }
}

// ---------- validation ----------

function checkCountPair(
  errors: FormErrors,
  rule: RuleForm,
  [minField, maxField]: readonly [RuleField, RuleField],
  keys: { invalid: string; order: string },
): void {
  const min = rule[minField] as string;
  const max = rule[maxField] as string;
  const minOk = !min.trim() || NON_NEGATIVE_INTEGER.test(min.trim());
  const maxOk = !max.trim() || NON_NEGATIVE_INTEGER.test(max.trim());
  if (!minOk) errors[ruleErrorKey(rule, minField)] = keys.invalid;
  if (!maxOk) errors[ruleErrorKey(rule, maxField)] = keys.invalid;
  if (minOk && maxOk && min.trim() && max.trim() && Number(min) > Number(max)) errors[ruleErrorKey(rule, maxField)] = keys.order;
}

/** The datatype a rule's values have: its own, else that of the property it constrains. */
function valueType(rule: RuleForm, pathDatatype: (ref: string) => string | null | undefined): string | null {
  return rule.datatype.trim() || pathDatatype(rule.pathRef) || null;
}

function checkBound(errors: FormErrors, rule: RuleForm, field: 'minValue' | 'maxValue', type: string | null): void {
  const text = rule[field].trim();
  if (!text) return;
  // An unchanged value keeps its stored spelling, whatever it is.
  if (type === 'integer' && !INTEGER.test(text)) errors[ruleErrorKey(rule, field)] = 'ontologyPage.form.errors.integerValue';
  else if (type === 'decimal' && !DECIMAL.test(text)) errors[ruleErrorKey(rule, field)] = 'ontologyPage.form.errors.numberValue';
}

function validateRule(errors: FormErrors, rule: RuleForm, pathDatatype: (ref: string) => string | null | undefined): void {
  if (!rule.pathRef) errors[ruleErrorKey(rule, 'pathRef')] = 'ontologyPage.form.errors.pathRequired';
  checkCountPair(errors, rule, ['minCount', 'maxCount'], {
    invalid: 'ontologyPage.form.errors.countInvalid',
    order: 'ontologyPage.form.errors.countOrder',
  });
  checkCountPair(errors, rule, ['minLength', 'maxLength'], {
    invalid: 'ontologyPage.form.errors.lengthInvalid',
    order: 'ontologyPage.form.errors.lengthOrder',
  });
  const type = valueType(rule, pathDatatype);
  checkBound(errors, rule, 'minValue', type);
  checkBound(errors, rule, 'maxValue', type);
  if (!PATTERN_FLAGS.test(rule.flags.trim())) errors[ruleErrorKey(rule, 'flags')] = 'ontologyPage.form.errors.flagsInvalid';
}

export function validateElementForm(
  mode: FormMode,
  form: ElementForm,
  pathDatatype: (ref: string) => string | null | undefined = () => null,
): FormErrors {
  const errors: FormErrors = {};
  if (isRequired('labelZh', mode) && !form.labelZh.trim()) errors.labelZh = 'review.edit.errors.labelZhRequired';
  if (mode.creating) {
    const name = form.localName.trim();
    const pascal = usesPascalCase(mode.kind);
    if (!name) errors.localName = 'review.edit.errors.localNameRequired';
    else if (!(pascal ? PASCAL_CASE : CAMEL_CASE).test(name)) {
      errors.localName = pascal ? 'review.edit.errors.localNamePascal' : 'review.edit.errors.localNameCamel';
    } else if (name.length > LOCAL_NAME_MAX) errors.localName = 'ontologyPage.form.errors.localNameTooLong';
  }
  const fields = formFields(mode.kind);
  if (fields.has('domainRef') && isRequired('domainRef', mode) && !form.domainRef) {
    errors.domainRef = mode.kind === 'constraint' ? 'ontologyPage.form.errors.targetRequired' : 'review.edit.errors.domainRequired';
  }
  if (fields.has('rangeRef') && isRequired('rangeRef', mode) && !form.rangeRef) errors.rangeRef = 'review.edit.errors.rangeRequired';
  if (fields.has('datatype') && isRequired('datatype', mode) && !(DATATYPES as readonly string[]).includes(form.datatype)) {
    errors.datatype = 'review.edit.errors.datatypeRequired';
  }
  if (mode.kind === 'constraint') for (const rule of form.rules) validateRule(errors, rule, pathDatatype);
  return errors;
}

// ---------- writing ----------

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function intOrNull(value: string): number | null {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function parseSynonyms(text: string, lang: Synonym['lang']): Synonym[] {
  return text
    .split(SYNONYM_SEPARATOR)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => ({ lang, text: part }));
}

/** Datatype of a new literal: none for plain text, else the rule's or the property's datatype. */
function literalDatatype(type: string | null): string | null {
  return !type || type === 'string' ? null : type;
}

function literal(text: string, datatype: string | null): RdfValue {
  return { iri: null, lexical: text, datatype, lang: null };
}

function allowedValues(form: RuleForm, type: string | null): Pick<ConstraintRuleFields, 'allowedValues' | 'allowedValuesLost'> {
  const lines = form.allowedValues
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const stored = form.source?.allowedValues ?? null;
  if (lines.length === 0) {
    return { allowedValues: stored && stored.length === 0 ? [] : null, allowedValuesLost: form.source?.allowedValuesLost ?? false };
  }
  const values = lines.map((line): RdfValue => {
    const kept = stored?.find((value) => valueText(value) === line);
    if (kept) return kept;
    return IRI_LIKE.test(line) ? { iri: line, lexical: null, datatype: null, lang: null } : literal(line, literalDatatype(type));
  });
  return { allowedValues: values, allowedValuesLost: false };
}

function boundType(text: string, type: string | null): string | null {
  if (type) return literalDatatype(type);
  if (INTEGER.test(text)) return 'integer';
  if (DECIMAL.test(text)) return 'decimal';
  return null;
}

/** [inclusive, exclusive] bounds; values the user left alone keep their stored spelling. */
function bounds(
  text: string,
  exclusive: boolean,
  storedInclusive: RdfValue | null | undefined,
  storedExclusive: RdfValue | null | undefined,
  type: string | null,
): [RdfValue | null, RdfValue | null] {
  const trimmed = text.trim();
  const stored = storedInclusive ?? storedExclusive ?? null;
  const storedIsExclusive = !storedInclusive && Boolean(storedExclusive);
  const unchangedText = stored !== null && valueText(stored) === trimmed;
  if (unchangedText && exclusive === storedIsExclusive) return [storedInclusive ?? null, storedExclusive ?? null];
  if (!trimmed) return [null, null];
  const value = unchangedText ? stored : literal(trimmed, boundType(trimmed, type));
  return exclusive ? [null, value] : [value, null];
}

function messages(form: RuleForm): LangText[] {
  const stored = form.source?.message ?? [];
  const slots = messageSlots(stored);
  const slot = (text: string, original: LangText): LangText[] => {
    const trimmed = text.trim();
    if (!trimmed) return [];
    return trimmed === original.text.trim() ? [original] : [{ ...original, text: trimmed }];
  };
  const result = stored.flatMap((message, index) => {
    if (index === slots.zh) return slot(form.messageZh, message);
    if (index === slots.en) return slot(form.messageEn, message);
    return [message];
  });
  if (slots.zh < 0 && form.messageZh.trim()) result.push({ lang: 'zh', text: form.messageZh.trim() });
  if (slots.en < 0 && form.messageEn.trim()) result.push({ lang: 'en', text: form.messageEn.trim() });
  return result;
}

export function ruleFromForm(form: RuleForm, pathDatatype: (ref: string) => string | null | undefined = () => null): ConstraintRuleFields {
  const source = form.source;
  const type = valueType(form, pathDatatype);
  const [minInclusive, minExclusive] = bounds(form.minValue, form.minExclusive, source?.minInclusive, source?.minExclusive, type);
  const [maxInclusive, maxExclusive] = bounds(form.maxValue, form.maxExclusive, source?.maxInclusive, source?.maxExclusive, type);
  return {
    pathRef: form.pathRef,
    classRef: form.classRef || null,
    minCount: intOrNull(form.minCount),
    maxCount: intOrNull(form.maxCount),
    datatype: textOrNull(form.datatype),
    nodeKind: source?.nodeKind ?? null,
    ...allowedValues(form, type),
    minInclusive,
    maxInclusive,
    minExclusive,
    maxExclusive,
    minLength: intOrNull(form.minLength),
    maxLength: intOrNull(form.maxLength),
    // Spaces are part of a regular expression; only an empty pattern means none.
    pattern: form.pattern === '' ? null : form.pattern,
    flags: textOrNull(form.flags),
    message: messages(form),
  };
}

/** Every field the kind has, as the form holds them; `localName` only when creating. */
function allFields(mode: FormMode, form: ElementForm, pathDatatype: (ref: string) => string | null | undefined): ElementFields {
  const fields: ElementFields = {};
  if (mode.creating) fields.localName = form.localName.trim();
  fields.labelZh = textOrNull(form.labelZh);
  fields.labelEn = textOrNull(form.labelEn);
  fields.definitionZh = textOrNull(form.definitionZh);
  fields.definitionEn = textOrNull(form.definitionEn);
  if (mode.kind !== 'constraint') fields.synonyms = [...parseSynonyms(form.synonymsZh, 'zh'), ...parseSynonyms(form.synonymsEn, 'en')];
  switch (mode.kind) {
    case 'entity_type':
      fields.parentRef = form.parentRef || null;
      break;
    case 'relation_type':
      fields.domainRef = form.domainRef || null;
      fields.rangeRef = form.rangeRef || null;
      fields.inverseRef = form.inverseRef || null;
      fields.required = form.required;
      fields.multiple = form.multiple;
      break;
    case 'property':
      fields.domainRef = form.domainRef || null;
      fields.datatype = (form.datatype || null) as Datatype | null;
      fields.unit = textOrNull(form.unit);
      fields.required = form.required;
      fields.multiple = form.multiple;
      break;
    case 'constraint':
      fields.domainRef = form.domainRef || null;
      fields.rules = form.rules.map((rule) => ruleFromForm(rule, pathDatatype));
      break;
  }
  return fields;
}

/** JSON with sorted keys and without unset values, to compare field values. */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, inner: unknown) => {
    if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
      return Object.fromEntries(
        Object.entries(inner as Record<string, unknown>)
          .filter(([, child]) => child !== null && child !== undefined)
          .sort(([a], [b]) => a.localeCompare(b)),
      );
    }
    return inner;
  });
}

/**
 * The fields to send. A create carries every field of its kind; an update only those that differ
 * from `initial` (the form as it was opened), since a field left out keeps its current value.
 */
export function formToFields(
  mode: FormMode,
  form: ElementForm,
  initial: ElementForm,
  pathDatatype: (ref: string) => string | null | undefined = () => null,
): ElementFields {
  const next = allFields(mode, form, pathDatatype);
  if (mode.creating) return next;
  const before = allFields(mode, initial, pathDatatype) as Record<string, unknown>;
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => canonical(value) !== canonical(before[key])));
}
