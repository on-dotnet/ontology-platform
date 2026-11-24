import { ArrowRight, ArrowRightLeft, CircleAlert, CircleCheck, FilePlus, PenLine, RotateCcw, ShieldAlert, Trash2, type LucideIcon } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { NativeSelect } from '@/components/ui/native-select';
import { Skeleton } from '@/components/ui/skeleton';
import { DATATYPES, type Datatype, type ElementKind, type OntologySummary } from '@/features/ontologies/api';
import { cn } from '@/lib/cn';

import {
  CHANGE_LEVELS,
  useComparison,
  WORKING,
  type ChangeLevel,
  type Comparison,
  type ElementChange,
  type FieldChange,
  type ReleaseSummary,
} from './api';

const levelStyle: Record<ChangeLevel, { tone: BadgeTone; icon: LucideIcon; text: string }> = {
  breaking: { tone: 'error', icon: ShieldAlert, text: 'text-error-strong' },
  review: { tone: 'warning', icon: CircleAlert, text: 'text-warning-strong' },
  compatible: { tone: 'success', icon: CircleCheck, text: 'text-success-strong' },
};

/** The number of changes per level, each with its icon, color and name. */
export function LevelCounts({ counts, className }: { counts: Comparison['counts']; className?: string }) {
  const { t } = useTranslation();
  return (
    <ul aria-label={t('releases.compare.countsLabel')} className={cn('flex flex-wrap gap-2', className)}>
      {CHANGE_LEVELS.map((level) => {
        const { tone, icon: Icon } = levelStyle[level];
        return (
          <li key={level}>
            <Badge tone={tone} className="tabular-nums">
              <Icon aria-hidden />
              {t('releases.compare.levelCount', { level: t(`releases.compare.levels.${level}`), count: counts[level] })}
            </Badge>
          </li>
        );
      })}
    </ul>
  );
}

const changeStyle: Record<ElementChange['change'], { tone: BadgeTone; icon: LucideIcon }> = {
  added: { tone: 'primary', icon: FilePlus },
  removed: { tone: 'error', icon: Trash2 },
  changed: { tone: 'secondary', icon: PenLine },
  restored: { tone: 'success', icon: RotateCcw },
};

function ChangeBadge({ change }: { change: ElementChange['change'] }) {
  const { t } = useTranslation();
  const { tone, icon: Icon } = changeStyle[change];
  return (
    <Badge tone={tone}>
      <Icon aria-hidden />
      {t(`releases.compare.change.${change}`)}
    </Badge>
  );
}

// ---------- field values ----------

/** The review form's names for element fields; references are named after what they point to. */
const FIELD_LABEL_KEYS: Record<string, string> = {
  labelZh: 'review.fields.labelZh',
  labelEn: 'review.fields.labelEn',
  definitionZh: 'review.fields.definitionZh',
  definitionEn: 'review.fields.definitionEn',
  synonyms: 'review.fields.synonyms',
  parentId: 'review.fields.parentRef',
  domainId: 'review.fields.domainRef',
  rangeId: 'review.fields.rangeRef',
  inverseId: 'review.fields.inverseRef',
  datatype: 'review.fields.datatype',
  unit: 'review.fields.unit',
  required: 'review.fields.required',
  multiple: 'review.fields.multiple',
  autoShape: 'review.fields.autoShape',
  rules: 'releases.compare.fields.rules',
  turtle: 'releases.compare.fields.turtle',
};

function fieldLabel(t: TFunction, field: string, kind: ElementKind): string {
  // A property's domain is the object type it belongs to; a constraint's is the type it checks.
  if (field === 'domainId' && kind === 'property') return t('review.fields.propertyDomainRef');
  if (field === 'domainId' && kind === 'constraint') return t('review.fields.targetRef');
  const key = FIELD_LABEL_KEYS[field];
  return key ? t(key) : t('releases.compare.fields.other');
}

/** Long or structured values are only said to have changed. */
const SUMMARIZED: Record<string, string> = { rules: 'releases.compare.rulesChanged', turtle: 'releases.compare.turtleChanged' };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isDatatype(value: string): value is Datatype {
  return (DATATYPES as readonly string[]).includes(value);
}

/** A field value as text: references by name, synonyms as a list, booleans as yes / no. */
export function formatFieldValue(t: TFunction, field: string, value: unknown): string {
  if (value === null || value === undefined) return t('releases.compare.none');
  if (field.endsWith('Id') && isRecord(value)) {
    return typeof value.label === 'string' && value.label ? value.label : t('releases.compare.missingRef');
  }
  if (field === 'synonyms' && Array.isArray(value)) {
    const texts = value.flatMap((synonym) => (isRecord(synonym) && typeof synonym.text === 'string' ? [synonym.text] : []));
    return texts.length > 0 ? texts.join(t('common.listSeparator')) : t('releases.compare.none');
  }
  if (typeof value === 'boolean') return t(value ? 'releases.compare.yes' : 'releases.compare.no');
  if (field === 'datatype' && typeof value === 'string' && isDatatype(value)) return t(`datatypes.${value}`);
  if (typeof value === 'string') return value.trim() ? value : t('releases.compare.empty');
  if (typeof value === 'number') return String(value);
  return t('releases.compare.valueChanged');
}

function FieldChanges({ change }: { change: ElementChange }) {
  const { t } = useTranslation();
  return (
    <dl className="space-y-1 text-xs">
      {change.fields.map((field) => {
        const summary = SUMMARIZED[field.field];
        return (
          <div key={field.field} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <dt className="shrink-0 text-muted-foreground">
              {fieldLabel(t, field.field, change.kind)}
              {t('common.colon')}
            </dt>
            <dd className="min-w-0 text-foreground">{summary ? t(summary) : <FieldValues field={field} />}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function FieldValues({ field }: { field: FieldChange }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <span className="break-words text-muted-foreground line-through decoration-muted-foreground/60">
        {formatFieldValue(t, field.field, field.before)}
      </span>
      <ArrowRight className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      <span className="sr-only">{t('releases.compare.becomes')}</span>
      <span className="break-words font-medium">{formatFieldValue(t, field.field, field.after)}</span>
    </span>
  );
}

function ChangeRow({ change }: { change: ElementChange }) {
  const { t } = useTranslation();
  const label = change.label || t('releases.compare.unnamed');
  return (
    <li className="space-y-1.5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn('min-w-0 break-words font-medium text-foreground', change.kind === 'axiom' && 'font-mono text-xs')}>{label}</span>
        <Badge tone="neutral">{t(`kinds.${change.kind}`)}</Badge>
        <ChangeBadge change={change.change} />
      </div>
      {change.fields.length > 0 ? <FieldChanges change={change} /> : null}
    </li>
  );
}

/** Changes grouped by level, most severe first, each group with its count, icon and color. */
export function ComparisonResult({ comparison }: { comparison: Comparison }) {
  const { t } = useTranslation();
  const headingId = useId();
  if (comparison.changes.length === 0) {
    return (
      <EmptyState
        icon={CircleCheck}
        tone="success"
        title={t('releases.compare.noChangesTitle')}
        description={t('releases.compare.noChangesDescription')}
        headingLevel="h3"
        className="py-10"
      />
    );
  }
  return (
    <div className="space-y-5">
      <LevelCounts counts={comparison.counts} />
      {CHANGE_LEVELS.map((level) => {
        const changes = comparison.changes.filter((change) => change.level === level);
        if (changes.length === 0) return null;
        const { icon: Icon, text } = levelStyle[level];
        return (
          <section key={level} aria-labelledby={`${headingId}-${level}`}>
            <div className="flex items-center gap-1">
              <h3 id={`${headingId}-${level}`} className={cn('flex items-center gap-2 text-sm font-semibold', text)}>
                <Icon className="size-4" aria-hidden />
                {t('releases.compare.levelCount', { level: t(`releases.compare.levels.${level}`), count: changes.length })}
              </h3>
              <InfoTip label={t('releases.compare.levelInfoLabel', { level: t(`releases.compare.levels.${level}`) })}>
                {t(`releases.compare.levelInfo.${level}`)}
              </InfoTip>
            </div>
            <ul className="divide-y divide-border">
              {changes.map((change) => (
                <ChangeRow key={change.elementId} change={change} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function ComparisonSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy className="space-y-3">
      <span className="sr-only">{t('common.loading')}</span>
      <div className="flex gap-2">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-6 w-24" />
      </div>
      <Skeleton className="h-12 rounded-lg" />
      <Skeleton className="h-12 rounded-lg" />
    </div>
  );
}

interface CompareCardProps {
  ontology: OntologySummary;
  /** Newest first, as the releases list returns them; at least one. */
  releases: readonly ReleaseSummary[];
}

/** Version page comparison: a release against another release or the working version. */
export function CompareCard({ ontology, releases }: CompareCardProps) {
  const { t } = useTranslation();
  const fromId = useId();
  const toId = useId();
  const current = releases.find((release) => release.isActive) ?? releases[0];
  // null follows the default (current release → working version), also after a new release is published.
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const known = (id: string | null): id is string => releases.some((release) => release.id === id);
  const fromValue = known(from) ? from : (current?.id ?? '');
  const toValue = known(to) ? to : WORKING;
  const query = useComparison(ontology.id, fromValue || undefined, toValue);

  const option = (release: ReleaseSummary) =>
    t(release.isActive ? 'releases.compare.currentOption' : 'releases.compare.option', { version: release.version, title: release.title });

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <ArrowRightLeft className="size-4.5 text-primary-strong" aria-hidden />
          <CardTitle>{t('releases.compare.title')}</CardTitle>
          <InfoTip label={t('common.aboutPage', { title: t('releases.compare.title') })}>{t('releases.compare.info')}</InfoTip>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={fromId} className="text-sm font-medium text-muted-foreground">
            {t('releases.compare.fromLabel')}
          </label>
          <NativeSelect id={fromId} value={fromValue} onChange={(event) => setFrom(event.target.value)} containerClassName="w-56 max-w-full" className="h-9">
            {releases.map((release) => (
              <option key={release.id} value={release.id}>
                {option(release)}
              </option>
            ))}
          </NativeSelect>
          <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
          <label htmlFor={toId} className="text-sm font-medium text-muted-foreground">
            {t('releases.compare.toLabel')}
          </label>
          <NativeSelect id={toId} value={toValue} onChange={(event) => setTo(event.target.value)} containerClassName="w-56 max-w-full" className="h-9">
            <option value={WORKING}>{t('releases.compare.working')}</option>
            {releases.map((release) => (
              <option key={release.id} value={release.id}>
                {option(release)}
              </option>
            ))}
          </NativeSelect>
        </div>
      </CardHeader>
      <CardContent>
        <QueryState query={query} loading={<ComparisonSkeleton />} errorTitle={t('releases.compare.failedTitle')}>
          {(comparison) => <ComparisonResult comparison={comparison} />}
        </QueryState>
      </CardContent>
    </Card>
  );
}
