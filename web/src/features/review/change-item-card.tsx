import { ArrowRight, Check, ChevronDown, Pencil, Quote, Waypoints, X } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tooltip } from '@/components/ui/tooltip';
import { DATATYPES } from '@/features/ontologies/api';
import { AxiomBadge, AxiomFragment, ConstraintRules } from '@/features/ontology/element-content';
import { cn } from '@/lib/cn';

import { isAiSource, type ChangeItem, type ChangeSetSource, type Decision, type ElementFields, type MatchDecision, type RejectReason } from './api';
import { BindingComparison, BindingNotices, bindingSentence, isBindingKind } from './binding-item';
import { AiSuggestionBadge, ConfidenceBadge, DecisionBadge, FlagTips, OpBadge, RejectReasonBadge } from './item-badges';
import { ItemImpact } from './item-impact';
import { MatchNotice } from './match-notice';
import { MetricItem } from './metric-item';
import { ResolutionNotice } from './resolution-notice';
import {
  COMPARED_FIELDS,
  effectiveFields,
  fieldText,
  isEditable,
  itemLabel,
  refLabel,
  shownFields,
  type ComparedField,
  type FieldFormat,
  type RefContext,
} from './item-fields';

interface ChangeItemCardProps {
  item: ChangeItem;
  /** The change set the item belongs to. */
  changeSetId: string;
  merged: boolean;
  context: RefContext;
  source: ChangeSetSource;
  selected: boolean;
  onSelect: () => void;
  /** Id of the evidence panel the button opens under the card (stacked layout); unset when it selects. */
  evidencePanelId?: string;
  /** Accept / reject / edit are offered (reviewer role, change set still open). */
  canDecide: boolean;
  busy: boolean;
  onDecide: (decision: Decision, rejectReason?: RejectReason) => void;
  /** The reviewer's conclusion on the item's alignment record; null clears it. */
  onDecideMatch: (decision: MatchDecision) => void;
  onEdit: () => void;
  /** Offers the impact summary of updates and deletes, loaded from this ontology when opened. */
  impactOntologyId?: string;
}

/** One proposed change with its operation, AI label and confidence, flags, decision buttons and evidence entry. */
export function ChangeItemCard({
  item,
  changeSetId,
  merged,
  context,
  source,
  selected,
  onSelect,
  evidencePanelId,
  canDecide,
  busy,
  onDecide,
  onDecideMatch,
  onEdit,
  impactOntologyId,
}: ChangeItemCardProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const impactId = useId();
  const [showImpact, setShowImpact] = useState(false);
  const { targetElementId } = item;
  const isAi = isAiSource(source);
  const patch = effectiveFields(item);
  const skipMetric = item.kind === 'metric' && (source !== 'manual' || patch.metric === null);
  const hasImpact = !skipMetric && impactOntologyId !== undefined && targetElementId !== null && (item.op === 'update' || item.op === 'delete');
  // After merge, the server reads "before" from the live target, which may already have changed again.
  const mergedMetric = merged && item.kind === 'metric';
  const fields = mergedMetric ? patch : shownFields(item);
  const isBinding = isBindingKind(item.kind);
  const label = isBinding ? bindingSentence(t, item, context) : itemLabel(mergedMetric ? { ...item, before: null } : item, context, t);
  const isAxiom = item.kind === 'axiom';
  const localName = isAxiom || isBinding ? null : fields.localName;
  // Delete and restore show what the target holds now, so the reviewer sees what goes away or comes back.
  // A restore that another change set already did only adds to the element (see its notice).
  const showsCurrent = item.op === 'delete' || (item.op === 'restore' && item.resolution?.mode !== 'update');

  // Once the reviewer kept the two apart, there is no duplicate left to check. An unverified key
  // has a notice of its own in the card.
  const flags = item.flags.filter(
    (flag) => flag !== 'key_unverified' && !(flag === 'possible_duplicate' && item.match?.decision === 'different'),
  );

  // Pressing the active decision again returns the item to "pending".
  const toggle = (decision: Exclude<Decision, 'pending'>) => onDecide(item.decision === decision ? 'pending' : decision);

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        'rounded-xl border bg-card p-4 transition-colors',
        selected ? 'border-primary ring-1 ring-primary' : 'border-border',
        item.decision === 'rejected' && !selected && 'bg-muted/40',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <OpBadge op={item.op} />
        {isAi ? <AiSuggestionBadge /> : null}
        {isAi && item.confidence !== null ? <ConfidenceBadge confidence={item.confidence} /> : null}
        <FlagTips flags={flags} />
        {item.edited ? <Badge tone="neutral">{t('review.edited')}</Badge> : null}
        {!canDecide ? <DecisionBadge decision={item.decision} /> : null}
        {item.decision === 'rejected' && item.rejectReason ? <RejectReasonBadge reason={item.rejectReason} /> : null}
      </div>

      <h3
        id={titleId}
        className={cn(
          'mt-2 flex flex-wrap items-baseline gap-x-2 text-base font-semibold text-foreground',
        )}
      >
        <span className={cn(item.decision === 'rejected' && 'text-muted-foreground line-through')}>
          {isAxiom ? <AxiomBadge category={item.axiomCategory} /> : label}
        </span>
        {localName ? <span className="font-mono text-xs font-normal text-muted-foreground">{localName}</span> : null}
      </h3>

      {skipMetric ? (
        <InlineNotice tone="warning" announce={false} className="mt-2" title={t(merged ? 'reviewMetric.skipped' : 'reviewMetric.willSkip')}>
          {t(source !== 'manual' ? 'reviewMetric.manualOnly' : 'reviewMetric.nullDefinition')}
        </InlineNotice>
      ) : (
        <>
          {showsCurrent && !mergedMetric ? <p className="mt-1.5 text-xs font-medium text-muted-foreground">{t(`review.currentValue.${item.op}`)}</p> : null}
          {item.match ? (
            <MatchNotice item={item} match={item.match} changeSetId={changeSetId} canDecide={canDecide} busy={busy} onDecide={onDecideMatch} />
          ) : null}
          {item.resolution ? <ResolutionNotice item={item} resolution={item.resolution} /> : null}
          {isBinding ? <BindingNotices item={item} context={context} />
            : item.kind === 'metric' ? <MetricItem item={item} context={context} merged={merged} />
            : <ItemFacts item={item} fields={fields} context={context} />}
          {isBinding && item.op === 'update' ? <BindingComparison item={item} /> : null}
          {!isBinding && !mergedMetric && (item.op === 'update' || item.op === 'restore') ? (
            <UpdateComparison kind={item.kind} before={item.before} after={patch} context={context} />
          ) : null}
        </>
      )}
      {/* The rules above are the new ones; an update that changes them shows what they replace. */}
      {item.op === 'update' && item.kind === 'constraint' && item.before && effectiveFields(item).rules !== undefined ? (
        <section className="mt-2 space-y-1.5" aria-label={t('review.rulesBefore')}>
          <p className="text-xs font-medium text-muted-foreground">{t('review.rulesBefore')}</p>
          <ConstraintRules rules={item.before.rules ?? []} nameOf={(ref) => refLabel(ref, context)} />
        </section>
      ) : null}
      {item.rationale ? <p className="mt-2 text-xs text-muted-foreground">{t('review.rationale', { text: item.rationale })}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {canDecide ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={item.decision === 'accepted'}
              disabled={busy}
              onClick={() => toggle('accepted')}
              className="aria-pressed:border-success/50 aria-pressed:bg-success-soft aria-pressed:text-success-strong"
            >
              <Check aria-hidden />
              {t('review.accept')}
            </Button>
            <RejectSplitButton disabled={busy} pressed={item.decision === 'rejected'} onReject={() => toggle('rejected')} onReason={(reason) => onDecide('rejected', reason)} />
            {isEditable(item, context) ? (
              <Tooltip content={t('review.editItem')}>
                <Button variant="ghost" size="icon-sm" aria-label={t('review.editItemNamed', { name: label })} disabled={busy} onClick={onEdit}>
                  <Pencil aria-hidden />
                </Button>
              </Tooltip>
            ) : null}
          </>
        ) : null}
        {hasImpact ? (
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={showImpact}
            aria-controls={showImpact ? impactId : undefined}
            onClick={() => setShowImpact((value) => !value)}
            className="aria-expanded:bg-primary-soft aria-expanded:text-primary-strong"
          >
            <Waypoints aria-hidden />
            {showImpact ? t('review.impact.hide') : t('review.impact.show')}
          </Button>
        ) : null}
        {/* Only AI proposals cite sources; imports and manual edits have nothing to show. */}
        {isAi ? (
          <Button
            variant="ghost"
            size="sm"
            {...(evidencePanelId
              ? { 'aria-expanded': selected, 'aria-controls': selected ? evidencePanelId : undefined }
              : { 'aria-pressed': selected })}
            onClick={onSelect}
            className="ml-auto aria-expanded:bg-primary-soft aria-expanded:text-primary-strong aria-pressed:bg-primary-soft aria-pressed:text-primary-strong"
          >
            <Quote aria-hidden />
            {t('review.evidenceCount', { count: item.evidence.length })}
          </Button>
        ) : null}
      </div>
      {hasImpact && showImpact ? (
        <div id={impactId} role="region" aria-label={t('review.impact.label', { name: label })} className="mt-3">
          <ItemImpact ontologyId={impactOntologyId} item={{ ...item, targetElementId }} context={context} />
        </div>
      ) : null}
    </article>
  );
}

const REJECT_REASONS: readonly RejectReason[] = ['out_of_scope', 'incorrect', 'duplicate', 'keep_open'];

export function RejectSplitButton({ disabled, pressed, onReject, onReason }: {
  disabled: boolean;
  pressed?: boolean;
  onReject: () => void;
  onReason: (reason: RejectReason) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="inline-flex items-center">
      <Button variant="secondary" size="sm" aria-pressed={pressed} disabled={disabled} onClick={onReject}
        className="rounded-r-none aria-pressed:border-error/50 aria-pressed:bg-error-soft aria-pressed:text-error-strong">
        <X aria-hidden />{t('review.reject')}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger aria-label={t('review.rejectWithReason')} disabled={disabled} className="inline-flex h-8 items-center rounded-r-lg border border-l-0 border-border bg-card px-2 text-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
          <ChevronDown aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {REJECT_REASONS.map((reason) => (
            <DropdownMenuItem key={reason} onClick={() => onReason(reason)}>{t(`review.rejectReasons.${reason}`)}</DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function ItemFacts({ item, fields, context }: { item: ChangeItem; fields: ElementFields; context: RefContext }) {
  const { t } = useTranslation();
  const unknownType = t('review.unknownType');

  if (item.kind === 'axiom') {
    return (
      <>
        {item.axiomNote ? <p className="mt-1.5 text-sm text-foreground">{item.axiomNote}</p> : null}
        <AxiomFragment turtle={fields.turtle} />
      </>
    );
  }

  if (item.kind === 'constraint') {
    return (
      <div className="mt-1.5 space-y-2 text-sm">
        <ul className="flex flex-wrap gap-1.5">
          <li className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {t('review.facts.target', { name: refLabel(fields.domainRef, context) ?? unknownType })}
          </li>
        </ul>
        {fields.definitionZh || fields.definitionEn ? (
          <p className="line-clamp-3 text-muted-foreground">{fields.definitionZh ?? fields.definitionEn}</p>
        ) : null}
        <ConstraintRules rules={fields.rules ?? []} nameOf={(ref) => refLabel(ref, context)} />
      </div>
    );
  }

  const facts: string[] = [];
  if (item.kind === 'entity_type' && fields.parentRef) {
    facts.push(t('review.facts.parent', { name: refLabel(fields.parentRef, context) ?? unknownType }));
  }
  if (item.kind === 'property') {
    if (fields.domainRef) facts.push(t('review.facts.domain', { name: refLabel(fields.domainRef, context) ?? unknownType }));
    if (fields.datatype) facts.push(t('review.facts.datatype', { type: t(`datatypes.${fields.datatype}`) }));
    if (fields.unit) facts.push(t('review.facts.unit', { unit: fields.unit }));
  }
  if (item.kind === 'relation_type' && fields.inverseRef) {
    facts.push(t('review.facts.inverse', { name: refLabel(fields.inverseRef, context) ?? t('review.unknownElement') }));
  }
  if (item.kind !== 'entity_type') {
    if (fields.required) facts.push(t('review.facts.required'));
    if (fields.multiple) facts.push(t('review.facts.multiple'));
  }

  return (
    <div className="mt-1.5 space-y-1.5 text-sm">
      {item.kind === 'relation_type' && (fields.domainRef || fields.rangeRef) ? (
        <p className="flex flex-wrap items-center gap-1.5 font-medium text-foreground">
          <span>{refLabel(fields.domainRef, context) ?? unknownType}</span>
          <ArrowRight className="size-3.5 text-muted-foreground" aria-label={t('review.facts.pointsTo')} />
          <span>{refLabel(fields.rangeRef, context) ?? unknownType}</span>
        </p>
      ) : null}
      {fields.definitionZh || fields.definitionEn ? (
        <p className="line-clamp-3 text-muted-foreground">{fields.definitionZh ?? fields.definitionEn}</p>
      ) : null}
      {facts.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {facts.map((fact) => (
            <li key={fact} className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {fact}
            </li>
          ))}
        </ul>
      ) : null}
      {fields.synonyms && fields.synonyms.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t('review.facts.synonyms', { list: fields.synonyms.map((synonym) => synonym.text).join(t('common.listSeparator')) })}
        </p>
      ) : null}
    </div>
  );
}

/** i18n key of a compared field's label; references are named after what they mean for the kind. */
function fieldLabelKey(kind: ChangeItem['kind'], field: ComparedField): string {
  if (field === 'domainRef' && kind === 'property') return 'review.fields.propertyDomainRef';
  if (field === 'domainRef' && kind === 'constraint') return 'review.fields.targetRef';
  return `review.fields.${field}`;
}

interface UpdateComparisonProps {
  kind: ChangeItem['kind'];
  before: ElementFields | null;
  after: ElementFields;
  context: RefContext;
}

/** Before → after for the fields an update (or a restore with changes) sets. */
function UpdateComparison({ kind, before, after, context }: UpdateComparisonProps) {
  const { t } = useTranslation();
  const format: FieldFormat = {
    separator: t('common.listSeparator'),
    ref: (ref) => refLabel(ref, context) ?? t('review.unknownElement'),
    datatype: (datatype) => ((DATATYPES as readonly string[]).includes(datatype) ? t(`datatypes.${datatype}`) : datatype),
    flag: (value) => (value ? t('review.yes') : t('review.no')),
  };
  const rows = COMPARED_FIELDS.filter((field) => !(kind === 'metric' && field === 'unit') &&
    field in after && fieldText(before, field, format) !== fieldText(after, field, format));
  if (rows.length === 0) return null;
  return (
    <dl className="mt-2 space-y-1.5 rounded-lg border border-border bg-background p-3 text-sm">
      {rows.map((field) => (
        <div key={field} className="grid gap-1 sm:grid-cols-[6rem_1fr]">
          <dt className="text-xs font-medium text-muted-foreground">{t(fieldLabelKey(kind, field))}</dt>
          <dd className="min-w-0 space-y-0.5">
            <p className="text-muted-foreground line-through">
              <span className="sr-only">{t('review.before')}</span>
              {fieldText(before, field, format) || t('review.emptyValue')}
            </p>
            <p className="text-foreground">
              <span className="sr-only">{t('review.after')}</span>
              {fieldText(after, field, format) || t('review.emptyValue')}
            </p>
          </dd>
        </div>
      ))}
    </dl>
  );
}
