import { ArrowRight, Check, Pencil, Quote, X } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';

import type { ChangeItem, Decision, ElementFields } from './api';
import { AiSuggestionBadge, ConfidenceBadge, DecisionBadge, FlagTips } from './item-badges';
import { COMPARED_FIELDS, effectiveFields, fieldText, itemLabel, refLabel, type RefContext } from './item-fields';

interface ChangeItemCardProps {
  item: ChangeItem;
  context: RefContext;
  /** The change set was proposed by AI: items carry the AI label. */
  isAi: boolean;
  selected: boolean;
  onSelect: () => void;
  /** Accept / reject / edit are offered (reviewer role, change set still open). */
  canDecide: boolean;
  busy: boolean;
  onDecide: (decision: Decision) => void;
  onEdit: () => void;
}

/** One proposed change with its AI label, confidence, flags, decision buttons and evidence entry. */
export function ChangeItemCard({ item, context, isAi, selected, onSelect, canDecide, busy, onDecide, onEdit }: ChangeItemCardProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const fields = effectiveFields(item);
  const label = itemLabel(item, context);
  const localName = fields.localName ?? item.before?.localName;

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
        <Badge tone={item.op === 'create' ? 'primary' : 'secondary'}>{t(`review.op.${item.op}`)}</Badge>
        {isAi ? <AiSuggestionBadge /> : null}
        {item.confidence !== null ? <ConfidenceBadge confidence={item.confidence} /> : null}
        <FlagTips flags={item.flags} />
        {item.edited ? <Badge tone="neutral">{t('review.edited')}</Badge> : null}
        {!canDecide ? <DecisionBadge decision={item.decision} /> : null}
      </div>

      <h3 id={titleId} className="mt-2 flex flex-wrap items-baseline gap-x-2 text-base font-semibold text-foreground">
        <span className={cn(item.decision === 'rejected' && 'text-muted-foreground line-through')}>{label}</span>
        {localName ? <span className="font-mono text-xs font-normal text-muted-foreground">{localName}</span> : null}
      </h3>

      <ItemFacts item={item} fields={fields} context={context} />
      {item.op === 'update' ? <UpdateComparison before={item.before} after={fields} /> : null}
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
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={item.decision === 'rejected'}
              disabled={busy}
              onClick={() => toggle('rejected')}
              className="aria-pressed:border-error/50 aria-pressed:bg-error-soft aria-pressed:text-error-strong"
            >
              <X aria-hidden />
              {t('review.reject')}
            </Button>
            <Tooltip content={t('review.editItem')}>
              <Button variant="ghost" size="icon-sm" aria-label={t('review.editItemNamed', { name: label })} disabled={busy} onClick={onEdit}>
                <Pencil aria-hidden />
              </Button>
            </Tooltip>
          </>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={selected}
          onClick={onSelect}
          className="ml-auto aria-pressed:bg-primary-soft aria-pressed:text-primary-strong"
        >
          <Quote aria-hidden />
          {t('review.evidenceCount', { count: item.evidence.length })}
        </Button>
      </div>
    </article>
  );
}

function ItemFacts({ item, fields, context }: { item: ChangeItem; fields: ElementFields; context: RefContext }) {
  const { t } = useTranslation();
  const unknownType = t('review.unknownType');
  const facts: string[] = [];
  if (item.kind === 'entity_type' && fields.parentRef) {
    facts.push(t('review.facts.parent', { name: refLabel(fields.parentRef, context) ?? unknownType }));
  }
  if (item.kind === 'property') {
    if (fields.domainRef) facts.push(t('review.facts.domain', { name: refLabel(fields.domainRef, context) ?? unknownType }));
    if (fields.datatype) facts.push(t('review.facts.datatype', { type: t(`datatypes.${fields.datatype}`) }));
    if (fields.unit) facts.push(t('review.facts.unit', { unit: fields.unit }));
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

/** Before → after for the fields an update changes. */
function UpdateComparison({ before, after }: { before: ElementFields | null; after: ElementFields }) {
  const { t } = useTranslation();
  const separator = t('common.listSeparator');
  const rows = COMPARED_FIELDS.filter((field) => field in after && fieldText(before, field, separator) !== fieldText(after, field, separator));
  if (rows.length === 0) return null;
  return (
    <dl className="mt-2 space-y-1.5 rounded-lg border border-border bg-background p-3 text-sm">
      {rows.map((field) => (
        <div key={field} className="grid gap-1 sm:grid-cols-[6rem_1fr]">
          <dt className="text-xs font-medium text-muted-foreground">{t(`review.fields.${field}`)}</dt>
          <dd className="min-w-0 space-y-0.5">
            <p className="text-muted-foreground line-through">
              <span className="sr-only">{t('review.before')}</span>
              {fieldText(before, field, separator) || t('review.emptyValue')}
            </p>
            <p className="text-foreground">
              <span className="sr-only">{t('review.after')}</span>
              {fieldText(after, field, separator) || t('review.emptyValue')}
            </p>
          </dd>
        </div>
      ))}
    </dl>
  );
}
