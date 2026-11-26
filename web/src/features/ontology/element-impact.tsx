import { useQueryClient } from '@tanstack/react-query';
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
import { cn } from '@/lib/cn';

import { isStale, useSaveErrorMessage, useSaveEdits } from './edit-actions';
import { kindTone } from './element-list';

type CascadeEntry = Impact['cascade'][number];

/**
 * What a cascade update does to an element, by its kind (spec 002, section 6): subtypes lose their
 * parent, relations their inverse, constraints the rules that use the deleted element.
 */
const updateEffects: Partial<Record<ElementRef['kind'], 'parentCleared' | 'inverseCleared' | 'rulesRemoved'>> = {
  entity_type: 'parentCleared',
  relation_type: 'inverseCleared',
  constraint: 'rulesRemoved',
};

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
          { key: 'bindings', refs: data.bindings ?? [] },
          { key: 'inverse', refs: data.inverse ? [data.inverse] : [] },
        ].filter((group) => group.refs.length > 0);
        if (groups.length === 0) return <p className="text-sm text-muted-foreground">{t('ontologyPage.impact.none')}</p>;
        return (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {groups.map((group) => (
              <div key={group.key} className="contents">
                <dt className="text-muted-foreground">{t(`ontologyPage.impact.groups.${group.key}`, { count: group.refs.length })}</dt>
                <dd className="flex min-w-0 flex-wrap gap-x-3 gap-y-1">
                  {group.refs.map((ref) =>
                    // Bindings have no detail panel of their own: they are shown in their type's.
                    group.key === 'bindings' ? (
                      <span key={ref.id} className="max-w-full truncate font-medium text-foreground">
                        {ref.label || '—'}
                      </span>
                    ) : (
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
                    ),
                  )}
                </dd>
              </div>
            ))}
          </dl>
        );
      }}
    </QueryState>
  );
}

interface CascadeListProps {
  cascade: readonly CascadeEntry[];
  /** Name of an element in the reader's language; falls back to the server's label. */
  nameOf: (ref: ElementRef) => string;
}

/**
 * Everything deleting an element brings along, as the server will propose it (the transitive
 * cascade): elements deleted with it, and elements that only lose a reference.
 */
export function CascadeList({ cascade, nameOf }: CascadeListProps) {
  const { t } = useTranslation();
  if (cascade.length === 0) return <p className="text-sm text-muted-foreground">{t('ontologyPage.delete.noImpact')}</p>;
  const deleted = cascade.filter((entry) => entry.op === 'delete');
  const changed = cascade.filter((entry) => entry.op === 'update');
  const list = (entries: readonly CascadeEntry[], label: string) => (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">{label}</h3>
      <ul className="divide-y divide-border rounded-lg border border-border" aria-label={label}>
        {entries.map(({ op, element }) => {
          const effect = op === 'update' ? updateEffects[element.kind] : undefined;
          return (
            <li key={element.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-sm">
              <Badge tone={kindTone[element.kind]}>{t(`kind.${element.kind}`)}</Badge>
              <span className={cn('min-w-0 flex-1 truncate text-foreground', element.kind === 'axiom' && 'font-mono text-xs')}>{nameOf(element)}</span>
              {effect ? <span className="text-xs text-muted-foreground">{t(`ontologyPage.delete.effects.${effect}`)}</span> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
  return (
    <div className="space-y-4">
      <InlineNotice tone="warning" title={t('ontologyPage.delete.impactTitle', { count: cascade.length })}>
        {t('ontologyPage.delete.impactDescription')}
      </InlineNotice>
      {deleted.length > 0 ? list(deleted, t('ontologyPage.delete.deletedLabel', { count: deleted.length })) : null}
      {changed.length > 0 ? list(changed, t('ontologyPage.delete.changedLabel', { count: changed.length })) : null}
    </div>
  );
}

interface DeleteElementDialogProps {
  ontologyId: string;
  element: Element;
  /** Active elements, for names in the reader's language; undefined while they load. */
  all: readonly Element[] | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Confirms deleting an element and lists the full cascade; the server adds the cascade items on saving. */
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
  const message = useSaveErrorMessage();
  const queryClient = useQueryClient();
  const impact = useImpact(ontologyId, element.id);
  const { apply, mutation } = useSaveEdits(ontologyId);
  const [reloading, setReloading] = useState(false);
  const name = element.kind === 'axiom' ? t('ontologyPage.detail.axiomTitle') : elementName(element, language) || '—';
  const byId = new Map((all ?? []).map((item) => [item.id, item]));

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
      <DialogDescription>{apply ? t('ontologyPage.delete.description') : t('ontologyPage.delete.reviewDescription')}</DialogDescription>
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
          {(data) => <CascadeList cascade={data.cascade} nameOf={(ref) => refName(ref, byId, language)} />}
        </QueryState>

        <div className="flex justify-end gap-2 pt-2">
          <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
          {/* Not while the cascade is reloading: the list must show what the delete brings along. */}
          <Button variant="destructive" disabled={!impact.isSuccess || impact.isFetching} loading={mutation.isPending} onClick={confirm}>
            <Trash2 aria-hidden />
            {apply ? t('ontologyPage.delete.confirm') : t('ontologyPage.edit.submitForReview')}
          </Button>
        </div>
      </div>
    </>
  );
}
