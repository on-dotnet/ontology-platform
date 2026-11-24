import { describe, expect, it } from 'vitest';

import type { ConstraintRule } from '@/features/ontologies/api';
import { elementFixture } from '@/test/fixtures';

import { formToFields, ruleFromForm, ruleToForm, suggestLocalName, toElementForm, validateElementForm, type FormMode } from './element-form';

describe('local name suggestion', () => {
  it('turns the English name into PascalCase for object types and constraints', () => {
    expect(suggestLocalName('Steel slab', 'entity_type')).toBe('SteelSlab');
    expect(suggestLocalName('  molten-steel check ', 'constraint')).toBe('MoltenSteelCheck');
    expect(suggestLocalName('Café crème', 'entity_type')).toBe('CafeCreme');
  });

  it('turns the English name into camelCase for relations and properties', () => {
    expect(suggestLocalName('Slab thickness', 'property')).toBe('slabThickness');
    expect(suggestLocalName('is held by', 'relation_type')).toBe('isHeldBy');
    expect(suggestLocalName('CO2 content', 'property')).toBe('co2Content');
  });

  it('starts with a letter and is empty without usable letters', () => {
    expect(suggestLocalName('3D model', 'entity_type')).toBe('DModel');
    expect(suggestLocalName('钢水', 'entity_type')).toBe('');
    expect(suggestLocalName('a'.repeat(200), 'entity_type')).toHaveLength(128);
  });
});

describe('element form', () => {
  const create: FormMode = { kind: 'property', creating: true, imported: false };

  it('requires the names, references and datatype of a new element', () => {
    const errors = validateElementForm(create, toElementForm(undefined, 'property', '、'));
    expect(errors).toEqual({
      labelZh: 'review.edit.errors.labelZhRequired',
      localName: 'review.edit.errors.localNameRequired',
      domainRef: 'review.edit.errors.domainRequired',
      datatype: 'review.edit.errors.datatypeRequired',
    });
  });

  it('does not require a Chinese name, references or datatype of an imported element', () => {
    const imported = elementFixture({ kind: 'property', explicitIri: true, labelZh: null, domainId: null, datatype: null });
    const form = toElementForm(imported, 'property', '、');
    expect(validateElementForm({ kind: 'property', creating: false, imported: true }, form)).toEqual({});
  });

  it('sends only the fields that changed when updating', () => {
    const element = elementFixture({ kind: 'property', domainId: 'el-ladle', datatype: 'decimal', unit: 'mm', synonyms: [{ lang: 'zh', text: '厚' }] });
    const mode: FormMode = { kind: 'property', creating: false, imported: false };
    const initial = toElementForm(element, 'property', '、');
    expect(formToFields(mode, initial, initial)).toEqual({});
    expect(formToFields(mode, { ...initial, unit: 'cm', required: true }, initial)).toEqual({ unit: 'cm', required: true });
    expect(formToFields(mode, { ...initial, synonymsZh: '厚，厚度' }, initial)).toEqual({
      synonyms: [
        { lang: 'zh', text: '厚' },
        { lang: 'zh', text: '厚度' },
      ],
    });
  });
});

describe('constraint rules in the form', () => {
  const stored: ConstraintRule = {
    pathId: 'el-grade',
    classId: null,
    minCount: 1,
    maxCount: 1,
    datatype: 'string',
    nodeKind: 'Literal',
    allowedValues: [
      { iri: null, lexical: 'Q235', datatype: null, lang: null },
      { iri: 'https://example.org/steel#Q345', lexical: null, datatype: null, lang: null },
    ],
    allowedValuesLost: false,
    minInclusive: { iri: null, lexical: '01', datatype: 'integer', lang: null },
    maxExclusive: { iri: null, lexical: '10.0', datatype: 'decimal', lang: null },
    pattern: '^Q\\d+ ',
    flags: 'i',
    message: [
      { lang: 'zh-CN', text: '牌号不合法' },
      { lang: 'de', text: 'Ungültige Sorte' },
    ],
  };

  it('saves an unchanged rule exactly as stored', () => {
    const { pathId, classId, ...rest } = stored;
    expect(ruleFromForm(ruleToForm(stored))).toEqual({
      ...rest,
      pathRef: pathId,
      classRef: classId,
      minLength: null,
      maxLength: null,
      minExclusive: null,
      maxInclusive: null,
    });
  });

  it('keeps the stored spelling of untouched values and types new ones like the rule', () => {
    const form = ruleToForm(stored);
    const fields = ruleFromForm({
      ...form,
      allowedValues: `${form.allowedValues}\nQ390\nurn:steel:Q420`,
      maxValue: '12',
      maxExclusive: false,
      messageZh: '牌号不在允许范围内',
      messageEn: 'Grade not allowed',
    });
    expect(fields.allowedValues).toEqual([
      ...(stored.allowedValues ?? []),
      { iri: null, lexical: 'Q390', datatype: null, lang: null },
      { iri: 'urn:steel:Q420', lexical: null, datatype: null, lang: null },
    ]);
    expect(fields.minInclusive).toEqual(stored.minInclusive);
    expect(fields.maxInclusive).toEqual({ iri: null, lexical: '12', datatype: null, lang: null });
    expect(fields.maxExclusive).toBeNull();
    expect(fields.message).toEqual([
      { lang: 'zh-CN', text: '牌号不在允许范围内' },
      { lang: 'de', text: 'Ungültige Sorte' },
      { lang: 'en', text: 'Grade not allowed' },
    ]);
  });

  it('types new bounds with the datatype of the constrained property', () => {
    const fields = ruleFromForm({ ...ruleToForm({ pathId: 'el-temperature', allowedValuesLost: false }), minValue: '1500' }, (ref) =>
      ref === 'el-temperature' ? 'decimal' : null,
    );
    expect(fields.minInclusive).toEqual({ iri: null, lexical: '1500', datatype: 'decimal', lang: null });
  });

  it('checks counts, lengths, numbers and flags', () => {
    const element = elementFixture({ kind: 'constraint', domainId: 'el-ladle', rules: [stored] });
    const form = toElementForm(element, 'constraint', '、');
    const [rule] = form.rules;
    if (!rule) throw new Error('rule expected');
    const errors = validateElementForm({ kind: 'constraint', creating: false, imported: false }, {
      ...form,
      rules: [{ ...rule, pathRef: '', minCount: '2', maxCount: '1', minLength: '-1', datatype: 'integer', minValue: '1.5', maxValue: '', flags: 'g' }],
    });
    const key = (field: string) => `rule:${rule.key}:${field}`;
    expect(errors).toEqual({
      [key('pathRef')]: 'ontologyPage.form.errors.pathRequired',
      [key('maxCount')]: 'ontologyPage.form.errors.countOrder',
      [key('minLength')]: 'ontologyPage.form.errors.lengthInvalid',
      [key('minValue')]: 'ontologyPage.form.errors.integerValue',
      [key('flags')]: 'ontologyPage.form.errors.flagsInvalid',
    });
  });
});

describe('values the form leaves alone', () => {
  const withValues: ConstraintRule = {
    pathId: 'el-grade',
    classId: null,
    datatype: 'integer',
    allowedValues: [
      { iri: null, lexical: '', datatype: null, lang: null },
      { iri: null, lexical: ' Q235 ', datatype: null, lang: null },
      { iri: null, lexical: 'line\nbreak', datatype: null, lang: null },
    ],
    allowedValuesLost: false,
    minInclusive: { iri: null, lexical: '0.0', datatype: 'decimal', lang: null },
    maxInclusive: { iri: null, lexical: '1.5E3', datatype: 'double', lang: null },
    flags: 'g',
    message: [],
  };

  it('keeps the synonyms of a language whose text did not change, even with separators in them', () => {
    const element = elementFixture({
      synonyms: [
        { lang: 'zh', text: '铁水' },
        { lang: 'en', text: 'Steel, molten' },
      ],
    });
    const mode: FormMode = { kind: 'entity_type', creating: false, imported: false };
    const initial = toElementForm(element, 'entity_type', '、');
    expect(formToFields(mode, { ...initial, synonymsZh: '铁水、钢液' }, initial)).toEqual({
      synonyms: [
        { lang: 'zh', text: '铁水' },
        { lang: 'zh', text: '钢液' },
        { lang: 'en', text: 'Steel, molten' },
      ],
    });
    expect(validateElementForm(mode, { ...initial, synonymsEn: 'x'.repeat(201) })).toEqual({ synonymsEn: 'ontologyPage.form.errors.synonymTooLong' });
  });

  it('saves an untouched rule from the stored one, values the text cannot show included', () => {
    const fields = ruleFromForm(ruleToForm(withValues));
    expect(fields.allowedValues).toEqual(withValues.allowedValues);
    expect(fields.minInclusive).toEqual(withValues.minInclusive);
    expect(fields.maxInclusive).toEqual(withValues.maxInclusive);
    expect(fields.flags).toBe('g');
  });

  it('keeps untouched allowed values when other fields of the rule change, and reads new ones with their language', () => {
    const form = ruleToForm(withValues);
    expect(ruleFromForm({ ...form, minCount: '1' }).allowedValues).toEqual(withValues.allowedValues);
    const added = ruleFromForm({ ...form, allowedValues: 'Q235@zh\nQ345@en-GB\nuser@example.org' });
    expect(added.allowedValues).toEqual([
      { iri: null, lexical: 'Q235', datatype: null, lang: 'zh' },
      { iri: null, lexical: 'Q345', datatype: null, lang: 'en-GB' },
      { iri: null, lexical: 'user@example.org', datatype: 'integer', lang: null },
    ]);
  });

  it('does not check bounds and flags the form did not touch', () => {
    const element = elementFixture({ kind: 'constraint', domainId: 'el-ladle', rules: [withValues] });
    const mode: FormMode = { kind: 'constraint', creating: false, imported: true };
    const form = toElementForm(element, 'constraint', '、');
    expect(validateElementForm(mode, form)).toEqual({});
    const [rule] = form.rules;
    if (!rule) throw new Error('rule expected');
    const key = (field: string) => `rule:${rule.key}:${field}`;
    expect(validateElementForm(mode, { ...form, rules: [{ ...rule, minValue: '0.5', flags: 'gg' }] })).toEqual({
      [key('minValue')]: 'ontologyPage.form.errors.integerValue',
      [key('flags')]: 'ontologyPage.form.errors.flagsInvalid',
    });
  });

  it('brings an element outside the platform shape into it when its cardinality changes', () => {
    const element = elementFixture({ kind: 'property', explicitIri: true, autoShape: false, datatype: 'decimal' });
    const mode: FormMode = { kind: 'property', creating: false, imported: true, autoShape: false };
    const initial = toElementForm(element, 'property', '、');
    expect(formToFields(mode, { ...initial, labelEn: 'Molten steel temperature' }, initial)).toEqual({ labelEn: 'Molten steel temperature' });
    expect(formToFields(mode, { ...initial, multiple: true }, initial)).toEqual({ multiple: true, autoShape: true });
    expect(formToFields({ ...mode, autoShape: true }, { ...initial, multiple: true }, initial)).toEqual({ multiple: true });
  });
});
