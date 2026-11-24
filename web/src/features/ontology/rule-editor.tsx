import { Plus, Trash2 } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip } from '@/components/ui/tooltip';
import { DATATYPES, elementName, type Element } from '@/features/ontologies/api';

import { emptyRule, MAX_LENGTH, ruleErrorKey, type RuleField, type RuleForm } from './element-form';

interface RuleEditorProps {
  rules: readonly RuleForm[];
  /** Active elements: the properties and relations a rule may constrain, the object types it may require. */
  elements: readonly Element[];
  language: string;
  onChange: (rules: RuleForm[]) => void;
  fieldId: (key: string) => string;
  /** Translated error of a field, once it should show. */
  errorFor: (key: string) => string | undefined;
  onTouch: (key: string) => void;
}

/** Edits the rules of a constraint (spec 3.3): one card per rule, added and removed freely. */
export function RuleEditor({ rules, elements, language, onChange, fieldId, errorFor, onTouch }: RuleEditorProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const update = (key: string, changes: Partial<RuleForm>) => onChange(rules.map((rule) => (rule.key === key ? { ...rule, ...changes } : rule)));

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h3 id={headingId} className="text-sm font-semibold text-foreground">
        {t('ontologyPage.form.rules.title')}
      </h3>
      {rules.length === 0 ? <p className="text-sm text-muted-foreground">{t('rules.none')}</p> : null}
      {rules.map((rule, index) => (
        <RuleCard
          key={rule.key}
          rule={rule}
          index={index}
          elements={elements}
          language={language}
          onUpdate={(changes) => update(rule.key, changes)}
          onRemove={() => onChange(rules.filter((other) => other.key !== rule.key))}
          fieldId={fieldId}
          errorFor={errorFor}
          onTouch={onTouch}
        />
      ))}
      <Button variant="secondary" size="sm" onClick={() => onChange([...rules, emptyRule()])}>
        <Plus aria-hidden />
        {t('ontologyPage.form.rules.add')}
      </Button>
    </section>
  );
}

/** A one-field change of a rule. */
function patch<K extends keyof RuleForm>(key: K, value: RuleForm[K]): Partial<RuleForm> {
  return { [key]: value };
}

interface RuleCardProps extends Pick<RuleEditorProps, 'elements' | 'language' | 'fieldId' | 'errorFor' | 'onTouch'> {
  rule: RuleForm;
  index: number;
  onUpdate: (changes: Partial<RuleForm>) => void;
  onRemove: () => void;
}

function RuleCard({ rule, index, elements, language, onUpdate, onRemove, fieldId, errorFor, onTouch }: RuleCardProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const number = index + 1;
  const removeLabel = t('ontologyPage.form.rules.remove', { n: number });
  const id = (field: RuleField) => fieldId(ruleErrorKey(rule, field));
  const error = (field: RuleField) => errorFor(ruleErrorKey(rule, field));
  const describedBy = (field: RuleField) => (error(field) ? `${id(field)}-error` : undefined);
  const touch = (field: RuleField) => onTouch(ruleErrorKey(rule, field));

  const properties = elements.filter((element) => element.kind === 'property');
  const relations = elements.filter((element) => element.kind === 'relation_type');
  const types = elements.filter((element) => element.kind === 'entity_type');
  const known = new Set(elements.map((element) => element.id));
  const labelOf = (element: Element) => elementName(element, language) || '—';
  const datatypeKnown = rule.datatype === '' || (DATATYPES as readonly string[]).includes(rule.datatype);

  const field = (name: RuleField, label: string, control: ReactNode, required = false) => (
    <div className="space-y-2">
      <Label htmlFor={id(name)} required={required}>
        {label}
      </Label>
      {control}
      {error(name) ? (
        <p id={`${id(name)}-error`} className="text-sm text-error-strong">
          {error(name)}
        </p>
      ) : null}
    </div>
  );

  const text = (
    name: Exclude<RuleField, 'minExclusive' | 'maxExclusive'>,
    extra: { mono?: boolean; numeric?: boolean; placeholder?: string; maxLength?: number } = {},
  ) => (
    <Input
      id={id(name)}
      value={rule[name]}
      maxLength={extra.maxLength}
      inputMode={extra.numeric ? 'numeric' : undefined}
      placeholder={extra.placeholder}
      className={extra.mono ? 'font-mono' : undefined}
      aria-invalid={error(name) ? true : undefined}
      aria-describedby={describedBy(name)}
      onChange={(event) => onUpdate(patch(name, event.target.value))}
      onBlur={() => touch(name)}
    />
  );

  const bound = (valueField: 'minValue' | 'maxValue', modeField: 'minExclusive' | 'maxExclusive', label: string) =>
    field(
      valueField,
      label,
      <div className="flex gap-2">
        {text(valueField)}
        <NativeSelect
          aria-label={t(`ontologyPage.form.rules.${valueField}Mode`)}
          containerClassName="w-32 shrink-0"
          value={rule[modeField] ? 'exclusive' : 'inclusive'}
          onChange={(event) => onUpdate(patch(modeField, event.target.value === 'exclusive'))}
        >
          <option value="inclusive">{t('ontologyPage.form.rules.inclusive')}</option>
          <option value="exclusive">{t('ontologyPage.form.rules.exclusive')}</option>
        </NativeSelect>
      </div>,
    );

  return (
    <section aria-labelledby={headingId} className="space-y-4 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h4 id={headingId} className="text-sm font-semibold text-foreground">
          {t('ontologyPage.form.rules.ruleTitle', { n: number })}
        </h4>
        <Tooltip content={removeLabel}>
          <Button variant="ghost" size="icon-sm" aria-label={removeLabel} onClick={onRemove}>
            <Trash2 aria-hidden />
          </Button>
        </Tooltip>
      </div>

      {field(
        'pathRef',
        t('rules.columns.path'),
        <NativeSelect
          id={id('pathRef')}
          value={rule.pathRef}
          aria-required
          aria-invalid={error('pathRef') ? true : undefined}
          aria-describedby={describedBy('pathRef')}
          onChange={(event) => onUpdate({ pathRef: event.target.value })}
          onBlur={() => touch('pathRef')}
        >
          <option value="">{t('ontologyPage.form.rules.choosePath')}</option>
          {rule.pathRef && !known.has(rule.pathRef) ? <option value={rule.pathRef}>{t('rules.unknownPath')}</option> : null}
          {properties.length > 0 ? (
            <optgroup label={t('kind.property')}>
              {properties.map((element) => (
                <option key={element.id} value={element.id}>
                  {labelOf(element)}
                </option>
              ))}
            </optgroup>
          ) : null}
          {relations.length > 0 ? (
            <optgroup label={t('kind.relation_type')}>
              {relations.map((element) => (
                <option key={element.id} value={element.id}>
                  {labelOf(element)}
                </option>
              ))}
            </optgroup>
          ) : null}
        </NativeSelect>,
        true,
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {field('minCount', t('ontologyPage.form.rules.minCount'), text('minCount', { numeric: true }))}
        {field('maxCount', t('ontologyPage.form.rules.maxCount'), text('maxCount', { numeric: true }))}
        {field(
          'datatype',
          t('review.fields.datatype'),
          <NativeSelect id={id('datatype')} value={rule.datatype} onChange={(event) => onUpdate({ datatype: event.target.value })}>
            <option value="">{t('ontologyPage.form.rules.any')}</option>
            {datatypeKnown ? null : <option value={rule.datatype}>{/[^#/]+$/.exec(rule.datatype)?.[0] ?? rule.datatype}</option>}
            {DATATYPES.map((datatype) => (
              <option key={datatype} value={datatype}>
                {t(`datatypes.${datatype}`)}
              </option>
            ))}
          </NativeSelect>,
        )}
        {field(
          'classRef',
          t('ontologyPage.form.rules.classRef'),
          <NativeSelect id={id('classRef')} value={rule.classRef} onChange={(event) => onUpdate({ classRef: event.target.value })}>
            <option value="">{t('ontologyPage.form.rules.any')}</option>
            {rule.classRef && !known.has(rule.classRef) ? <option value={rule.classRef}>{t('review.unknownType')}</option> : null}
            {types.map((element) => (
              <option key={element.id} value={element.id}>
                {labelOf(element)}
              </option>
            ))}
          </NativeSelect>,
        )}
      </div>

      {field(
        'allowedValues',
        t('ontologyPage.form.rules.allowedValues'),
        <Textarea
          id={id('allowedValues')}
          rows={3}
          value={rule.allowedValues}
          placeholder={t('ontologyPage.form.rules.allowedValuesPlaceholder')}
          className="font-mono"
          onChange={(event) => onUpdate({ allowedValues: event.target.value })}
        />,
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {bound('minValue', 'minExclusive', t('ontologyPage.form.rules.minValue'))}
        {bound('maxValue', 'maxExclusive', t('ontologyPage.form.rules.maxValue'))}
        {field('minLength', t('ontologyPage.form.rules.minLength'), text('minLength', { numeric: true }))}
        {field('maxLength', t('ontologyPage.form.rules.maxLength'), text('maxLength', { numeric: true }))}
        {field('pattern', t('ontologyPage.form.rules.pattern'), text('pattern', { mono: true, maxLength: MAX_LENGTH.pattern }))}
        {field(
          'flags',
          t('ontologyPage.form.rules.flags'),
          text('flags', { mono: true, placeholder: t('ontologyPage.form.rules.flagsPlaceholder'), maxLength: MAX_LENGTH.flags }),
        )}
        {field('messageZh', t('ontologyPage.form.rules.messageZh'), text('messageZh', { maxLength: MAX_LENGTH.message }))}
        {field('messageEn', t('ontologyPage.form.rules.messageEn'), text('messageEn', { maxLength: MAX_LENGTH.message }))}
      </div>
    </section>
  );
}
