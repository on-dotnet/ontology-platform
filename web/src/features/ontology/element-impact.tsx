import { useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { RefreshCw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { elementName, ontologyKeys, useImpact, type Element, type ElementRef, type Impact } from '@/features/ontologies/api';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

import { isStale, useSaveEdits } from './edit-actions';
import { kindTone } from './element-list';

/** What happens to an element that refers to a deleted one (spec 002, section 6). */
export type ImpactEffect = 'deleted' | 'parentCleared' | 'inverseCleared' | 'rulesRemoved';

export interface ImpactEntry {
  ref: ElementRef;
  effect: ImpactEffect;
}

/**
 * Sorts the elements referring to `target` by what deleting it does to them: relations and
 * properties on it, constraints targeting it (or left without rules) and axioms mentioning it are
 * deleted; subtypes lose their parent, the inverse relation its inverse, other constraints the
 * rules that use it.
 */
export function impactEntries(impact: Impact, target: Pick<Element, 'id'>, all: readonly Element[]): ImpactEntry[] {
  const byId = new Map(all.map((element) => [element.id, element]));
  const constraintEffect = (ref: ElementRef): ImpactEffect => {
    const constraint = byId.get(ref.id);
    if (!constraint || constraint.domainId === target.id) return 'deleted';
    const kept = (constraint.rules ?? []).filter((rule) => rule.pathId !== target.id && rule.classId !== target.id);
    return kept.length === 0 ? 'deleted' : 'rulesRemoved';
  };
  const entries: ImpactEntry[] = [
    ...impact.relations.map((ref) => ({ ref, effect: 'deleted' as const })),
    ...impact.properties.map((ref) => ({ ref, effect: 'deleted' as const })),
    ...impact.constraints.map((ref) => ({ ref, effect: constraintEffect(ref) })),
    ...impact.axioms.map((ref) => ({ ref, effect: 'deleted' as const })),
    ...impact.subtypes.map((ref) => ({ ref, effect: 'parentCleared' as const })),
  ];
  // A relation on the element that is also its inverse goes anyway.
  if (impact.inverse && !entries.some((entry) => entry.ref.id === impact.inverse?.id)) {
    entries.push({ ref: impact.inverse, effect: 'inverseCleared' });
  }
  return entries;
}

function refName(ref: ElementRef, byId: ReadonlyMap<string, Element>, language: string): string {
  const element = byId.get(ref.id);
  return (element ? elementName(element, language) : '') || ref.label || '—';
}

interface ReferencedByProps {
  ontologyId: string;
  element: Pick<Element, 'id'>;
  /** Active elements, for names in the reader's language. */
  all: readonly Element[] | undefined;
  onSelect: (id: string) => void;
}

/** The "referenced by" block of the element panel: everything that points to the element. */
export function ReferencedBy({ ontologyId, element, all, onSelect }: ReferencedByProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const impact = useImpact(ontologyId, element.id);
  const byId = new Map((all ?? []).map((item) => [item.id, item]));
  return (
    <QueryState query={impact} loading={<Skeleton className="h-16 rounded-lg" />}>
      {(data) => {
        const groups = [
          { key: 'subtypes', refs: data.subtypes },
          { key: 'relations', refs: data.relations },
          { key: 'properties', refs: data.properties },
          { key: 'constraints', refs: data.constraints },
          { key: 'axioms', refs: data.axioms },
          { key: 'inverse', refs: data.inverse ? [data.inverse] : [] },
        ].filter((group) => group.refs.length > 0);
        if (groups.length === 0) return <p className="text-sm text-muted-foreground">{t('ontologyPage.impact.none')}</p>;
        return (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {groups.map((group) => (
              <div key={group.key} className="contents">
                <dt className="text-muted-foreground">{t(`ontologyPage.impact.groups.${group.key}`, { count: group.refs.length })}</dt>
                <dd className="flex min-w-0 flex-wrap gap-x-3 gap-y-1">
                  {group.refs.map((ref) => (
                    <button
                      key={ref.id}
                      type="button"
                      onClick={() => onSelect(ref.id)}
                      className={cn(
                        'max-w-full truncate rounded text-left font-medium text-primary-strong hover:underline',
                        ref.kind === 'axiom' && 'font-mono text-xs',
                      )}
                    >
                      {refName(ref, byId, language)}
                    </button>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        );
      }}
    </QueryState>
  );
}

interface DeleteElementDialogProps {
  ontologyId: string;
  element: Element;
  /** Active elements: they tell constraints that go from those that only lose rules. */
  all: UseQueryResult<Element[]>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Confirms deleting an element and lists what goes with it; the server adds the cascade items. */
export function DeleteElementDialog({ ontologyId, element, all, open, onOpenChange }: DeleteElementDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] w-[min(36rem,calc(100vw-2rem))] overflow-y-auto">
        {open ? <DeleteBody ontologyId={ontologyId} element={element} all={all} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function DeleteBody({ ontologyId, element, all, onDone }: Omit<DeleteElementDialogProps, 'open' | 'onOpenChange'> & { onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const message = useErrorMessage();
  const queryClient = useQueryClient();
  const impact = useImpact(ontologyId, element.id);
  const { apply, mutation } = useSaveEdits(ontologyId);
  const [reloading, setReloading] = useState(false);
  const name = element.kind === 'axiom' ? t('ontologyPage.detail.axiomTitle') : elementName(element, language) || '—';
  const ready = impact.isSuccess && all.isSuccess;

  const confirm = () =>
    mutation.mutate(
      {
        items: [{ op: 'delete', kind: element.kind, targetElementId: element.id, targetRevision: element.revision }],
        appliedTitle: t('ontologyPage.edit.deleted', { name }),
      },
      { onSuccess: onDone },
    );

  const reload = async () => {
    setReloading(true);
    try {
      await queryClient.invalidateQueries({ queryKey: ontologyKeys.all });
      mutation.reset();
    } finally {
      setReloading(false);
    }
  };

  return (
    <>
      <DialogTitle>{t('ontologyPage.delete.title', { name })}</DialogTitle>
      <DialogDescription>{t('ontologyPage.delete.description')}</DialogDescription>
      <div className="mt-5 space-y-4">
        {mutation.isError ? (
          isStale(mutation.error) ? (
            <InlineNotice
              tone="error"
              title={t('ontologyPage.form.staleTitle')}
              action={
                <Button variant="secondary" size="sm" loading={reloading} onClick={() => void reload()}>
                  <RefreshCw aria-hidden />
                  {t('ontologyPage.form.reload')}
                </Button>
              }
            >
              {t('ontologyPage.delete.staleDescription')}
            </InlineNotice>
          ) : (
            <InlineNotice tone="error" title={t('ontologyPage.delete.failedTitle')}>
              {message(mutation.error)}
            </InlineNotice>
          )
        ) : null}

        <QueryState query={impact} loading={<Skeleton className="h-24 rounded-lg" />}>
          {(data) => (
            <QueryState query={all} loading={<Skeleton className="h-24 rounded-lg" />}>
              {(elements) => <ImpactList entries={impactEntries(data, element, elements)} elements={elements} language={language} />}
            </QueryState>
          )}
        </QueryState>

        <div className="flex justify-end gap-2 pt-2">
          <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
          <Button variant="destructive" disabled={!ready} loading={mutation.isPending} onClick={confirm}>
            <Trash2 aria-hidden />
            {apply ? t('ontologyPage.delete.confirm') : t('ontologyPage.edit.submitForReview')}
          </Button>
        </div>
      </div>
    </>
  );
}

function ImpactList({ entries, elements, language }: { entries: readonly ImpactEntry[]; elements: readonly Element[]; language: string }) {
  const { t } = useTranslation();
  const byId = new Map(elements.map((element) => [element.id, element]));
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">{t('ontologyPage.delete.noImpact')}</p>;
  const deleted = entries.filter((entry) => entry.effect === 'deleted');
  const changed = entries.filter((entry) => entry.effect !== 'deleted');
  const list = (items: readonly ImpactEntry[], label: string) => (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">{label}</h3>
      <ul className="divide-y divide-border rounded-lg border border-border" aria-label={label}>
        {items.map((entry) => (
          <li key={entry.ref.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-sm">
            <Badge tone={kindTone[entry.ref.kind]}>{t(`kind.${entry.ref.kind}`)}</Badge>
            <span className={cn('min-w-0 flex-1 truncate text-foreground', entry.ref.kind === 'axiom' && 'font-mono text-xs')}>
              {refName(entry.ref, byId, language)}
            </span>
            {entry.effect !== 'deleted' ? <span className="text-xs text-muted-foreground">{t(`ontologyPage.delete.effects.${entry.effect}`)}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
  return (
    <div className="space-y-4">
      <InlineNotice tone="warning" title={t('ontologyPage.delete.impactTitle', { count: entries.length })}>
        {t('ontologyPage.delete.impactDescription')}
      </InlineNotice>
      {deleted.length > 0 ? list(deleted, t('ontologyPage.delete.deletedLabel', { count: deleted.length })) : null}
      {changed.length > 0 ? list(changed, t('ontologyPage.delete.changedLabel', { count: changed.length })) : null}
    </div>
  );
}
