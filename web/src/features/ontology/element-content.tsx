import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { WarnTip } from '@/components/feedback/hint-tip';
import { Badge } from '@/components/ui/badge';
import { DATATYPES, type ConstraintRule, type ConstraintRuleFields, type Element, type LangText, type RdfValue } from '@/features/ontologies/api';
import { cn } from '@/lib/cn';

export function AxiomBadge({ category }: { category: Element['axiomCategory'] }) {
  const { t } = useTranslation();
  return <Badge tone="neutral">{t(`statement.category.${category ?? 'other'}`)}</Badge>;
}

export function AxiomFragment({ turtle }: { turtle: string | null | undefined }) {
  const { t } = useTranslation();
  if (!turtle) return null;
  return (
    <details className="mt-1 min-w-0 text-sm">
      <summary className="w-fit cursor-pointer rounded text-primary-strong">{t('ontologyPage.axiom.fragment')}</summary>
      <TurtleBlock turtle={turtle} className="mt-1" />
    </details>
  );
}

/** A Turtle fragment (an axiom) as written, in a monospace block that wraps instead of widening the page. */
export function TurtleBlock({ turtle, className }: { turtle: string; className?: string }) {
  return (
    <pre
      className={cn(
        'max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-muted px-3 py-2',
        'font-mono text-xs leading-relaxed text-foreground',
        className,
      )}
    >
      {turtle}
    </pre>
  );
}

/** A stored rule (element ids) or a change item's rule (ids or temp refs). */
export type AnyRule = ConstraintRule | ConstraintRuleFields;

function rulePath(rule: AnyRule): string {
  return 'pathId' in rule ? rule.pathId : rule.pathRef;
}

function ruleClass(rule: AnyRule): string | null | undefined {
  return 'pathId' in rule ? rule.classId : rule.classRef;
}

/** Short form of an RDF value: an IRI's last segment, or a literal as written (with its language). */
export function formatRdfValue(value: RdfValue): string {
  if (value.iri) return /[^#/]+$/.exec(value.iri)?.[0] ?? value.iri;
  const text = value.lexical ?? '';
  return value.lang ? `${text}@${value.lang}` : text;
}

/** The message in the reader's language, else one without a language, else the first. */
export function pickText(texts: readonly LangText[] | undefined, language: string): string | undefined {
  if (!texts || texts.length === 0) return undefined;
  const prefix = language.slice(0, 2);
  return (texts.find((text) => text.lang?.slice(0, 2) === prefix) ?? texts.find((text) => !text.lang) ?? texts[0])?.text;
}

interface ConstraintRulesProps {
  rules: readonly AnyRule[];
  /** Name of the property, relation or object type a rule points to; undefined when unknown. */
  nameOf: (ref: string) => string | undefined;
  className?: string;
}

/** The rules of a constraint: path, count, value type, allowed values and message (spec 3.3). */
export function ConstraintRules({ rules, nameOf, className }: ConstraintRulesProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  if (rules.length === 0) return <p className={cn('text-sm text-muted-foreground', className)}>{t('rules.none')}</p>;

  const head = 'h-9 whitespace-nowrap px-3 text-left text-xs font-semibold text-muted-foreground';
  return (
    <div className={cn('overflow-x-auto rounded-lg border border-border', className)}>
      <table className="w-full border-collapse text-sm" aria-label={t('rules.tableLabel')}>
        <thead className="bg-muted">
          <tr>
            <th scope="col" className={head}>
              {t('rules.columns.path')}
            </th>
            <th scope="col" className={head}>
              {t('rules.columns.count')}
            </th>
            <th scope="col" className={head}>
              {t('rules.columns.type')}
            </th>
            <th scope="col" className={head}>
              {t('rules.columns.values')}
            </th>
            <th scope="col" className={head}>
              {t('rules.columns.message')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule, index) => {
            const path = rulePath(rule);
            const classRef = ruleClass(rule);
            const message = pickText(rule.message, language);
            return (
              <tr key={`${path}-${index}`} className="border-t border-border align-top">
                <td className="px-3 py-2 font-medium text-foreground">{nameOf(path) ?? t('rules.unknownPath')}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-foreground">{formatCount(rule.minCount, rule.maxCount, t)}</td>
                <td className="px-3 py-2 text-foreground">
                  <RuleTypes datatype={rule.datatype} className={classRef ? (nameOf(classRef) ?? t('review.unknownType')) : null} nodeKind={rule.nodeKind} />
                </td>
                <td className="min-w-40 px-3 py-2 text-foreground">
                  <RuleValues rule={rule} />
                </td>
                <td className="min-w-32 px-3 py-2 text-muted-foreground">{message ?? '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type Translate = ReturnType<typeof useTranslation>['t'];

function formatCount(min: number | null | undefined, max: number | null | undefined, t: Translate): string {
  const hasMin = min !== null && min !== undefined;
  const hasMax = max !== null && max !== undefined;
  if (hasMin && hasMax) return min === max ? t('rules.countExactly', { n: min }) : t('rules.countRange', { min, max });
  if (hasMin) return t('rules.countAtLeast', { n: min });
  if (hasMax) return t('rules.countAtMost', { n: max });
  return '—';
}

function formatLength(min: number | null | undefined, max: number | null | undefined, t: Translate): string | undefined {
  const hasMin = min !== null && min !== undefined;
  const hasMax = max !== null && max !== undefined;
  if (hasMin && hasMax) return t('rules.lengthRange', { min, max });
  if (hasMin) return t('rules.lengthAtLeast', { n: min });
  if (hasMax) return t('rules.lengthAtMost', { n: max });
  return undefined;
}

function RuleTypes({ datatype, className, nodeKind }: { datatype: string | null | undefined; className: string | null; nodeKind: AnyRule['nodeKind'] }) {
  const { t } = useTranslation();
  const parts: { key: string; text: string; mono?: boolean }[] = [];
  if (datatype) {
    const known = (DATATYPES as readonly string[]).includes(datatype);
    parts.push({ key: 'datatype', text: known ? t(`datatypes.${datatype}`) : (/[^#/]+$/.exec(datatype)?.[0] ?? datatype), mono: !known });
  }
  if (className) parts.push({ key: 'class', text: className });
  if (nodeKind) parts.push({ key: 'nodeKind', text: t(`rules.nodeKinds.${nodeKind}`) });
  if (parts.length === 0) return <>—</>;
  return (
    <ul className="space-y-0.5">
      {parts.map((part) => (
        <li key={part.key} className={part.mono ? 'font-mono text-xs' : undefined}>
          {part.text}
        </li>
      ))}
    </ul>
  );
}

function RuleValues({ rule }: { rule: AnyRule }) {
  const { t } = useTranslation();
  const range = [
    rule.minInclusive ? t('rules.minInclusive', { value: formatRdfValue(rule.minInclusive) }) : null,
    rule.minExclusive ? t('rules.minExclusive', { value: formatRdfValue(rule.minExclusive) }) : null,
    rule.maxInclusive ? t('rules.maxInclusive', { value: formatRdfValue(rule.maxInclusive) }) : null,
    rule.maxExclusive ? t('rules.maxExclusive', { value: formatRdfValue(rule.maxExclusive) }) : null,
  ].filter((part): part is string => part !== null);
  const length = formatLength(rule.minLength, rule.maxLength, t);
  const values = rule.allowedValues ?? [];
  const hasValues = values.length > 0 || rule.allowedValuesLost;

  if (!hasValues && range.length === 0 && !length && !rule.pattern) return <>—</>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
      {hasValues ? (
        <>
          <dt className="whitespace-nowrap text-xs text-muted-foreground">{t('rules.enumLabel')}</dt>
          <dd className="flex min-w-0 flex-wrap items-center gap-1">
            {values.map((value, index) => (
              <code key={index} className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs" title={value.iri ?? undefined}>
                {formatRdfValue(value)}
              </code>
            ))}
            {rule.allowedValuesLost ? <WarnTip label={t('rules.valuesLost.label')}>{t('rules.valuesLost.description')}</WarnTip> : null}
          </dd>
        </>
      ) : null}
      {range.length > 0 ? (
        <>
          <dt className="whitespace-nowrap text-xs text-muted-foreground">{t('rules.rangeLabel')}</dt>
          <dd className="tabular-nums">
            {range.map((part, index) => (
              <Fragment key={index}>
                {index > 0 ? t('rules.rangeSeparator') : null}
                <span className="whitespace-nowrap">{part}</span>
              </Fragment>
            ))}
          </dd>
        </>
      ) : null}
      {length ? (
        <>
          <dt className="whitespace-nowrap text-xs text-muted-foreground">{t('rules.lengthLabel')}</dt>
          <dd>{length}</dd>
        </>
      ) : null}
      {rule.pattern ? (
        <>
          <dt className="whitespace-nowrap text-xs text-muted-foreground">{t('rules.patternLabel')}</dt>
          <dd className="min-w-0 break-all font-mono text-xs">
            {rule.pattern}
            {rule.flags ? <span className="ml-1 text-muted-foreground">{t('rules.patternFlags', { flags: rule.flags })}</span> : null}
          </dd>
        </>
      ) : null}
    </dl>
  );
}
