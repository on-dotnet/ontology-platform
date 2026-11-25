import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowLeft, ArrowRight, CheckCheck, Combine, GitMerge, Network, Quote, Undo2 } from 'lucide-react';
import { Fragment, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { ErrorState } from '@/components/states/error-state';
import { LoadingState } from '@/components/states/loading-state';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Pagination } from '@/components/ui/pagination';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useCurrentUser } from '@/features/auth/api';
import { usePermissions } from '@/features/auth/permissions';
import { usePublishAssistantSelection } from '@/features/assistant/assistant-selection';
import { EvidenceExcerpt } from '@/features/documents/evidence-excerpt';
import { ELEMENT_KINDS, ontologyKeys, useElements, usePlatformSettings, type Element } from '@/features/ontologies/api';
import { codeMessage, useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';
import { usePagination } from '@/lib/pagination';
import { DESKTOP_QUERY, useMediaQuery } from '@/lib/use-media-query';

import {
  acceptsAll,
  changeSetKeys,
  decideItems,
  highConfidencePending,
  isAiSource,
  matchPlace,
  mergeChangeSet,
  patchItem,
  rejectChangeSet,
  replaceItemInCache,
  sameConceptPending,
  useChangeSet,
  type ChangeItem,
  type ChangeSetDetail,
  type ItemMatch,
  type ItemPatch,
  type MergeResult,
} from './api';
import { ChangeItemCard } from './change-item-card';
import { ChangeItemEditDialog } from './change-item-edit-dialog';
import { buildRefContext, itemLabel, type RefContext } from './item-fields';
import { DocumentName, SourceBadge } from './review-list-page';

function BackToList({ ontologyId }: { ontologyId?: string }) {
  const { t } = useTranslation();
  return (
    <Link
      to="/review"
      search={ontologyId ? { ontology: ontologyId } : {}}
      className="mb-3 inline-flex items-center gap-1.5 rounded text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-4" aria-hidden />
      {t('review.backToList')}
    </Link>
  );
}

export function ReviewDetailPage({ changeSetId }: { changeSetId: string }) {
  const { t } = useTranslation();
  const query = useChangeSet(changeSetId);
  // The URL names no ontology here; the assistant works on the change set's, once it is known.
  usePublishAssistantSelection({
    ontologyId: query.data?.ontologyId,
    ontologyStatus: query.isPending ? 'pending' : query.isError ? 'failed' : undefined,
  });
  if (query.isSuccess) return <ChangeSetLoaded changeSet={query.data} />;
  return (
    <>
      <BackToList />
      <PageHeader title={t('review.detailTitle')} />
      <QueryState query={query} loading={<LoadingState variant="detail" />}>
        {() => null}
      </QueryState>
    </>
  );
}

/**
 * Waits for the ontology's elements, which name the object types items refer to, and, for a change
 * set the user submitted, for the review mode, which decides whether they may review it.
 */
function ChangeSetLoaded({ changeSet }: { changeSet: ChangeSetDetail }) {
  const user = useCurrentUser();
  const own = user !== null && changeSet.createdBy === user.id;
  return own ? <OwnChangeSetLoaded changeSet={changeSet} /> : <ElementsLoaded changeSet={changeSet} own={false} selfReview={false} />;
}

function OwnChangeSetLoaded({ changeSet }: { changeSet: ChangeSetDetail }) {
  const settings = usePlatformSettings();
  return (
    <QueryState query={settings} loading={<LoadingState variant="detail" />}>
      {({ reviewMode }) => <ElementsLoaded changeSet={changeSet} own selfReview={reviewMode === 'single'} />}
    </QueryState>
  );
}

interface ElementsLoadedProps {
  changeSet: ChangeSetDetail;
  /** The current user submitted the change set. */
  own: boolean;
  /** Submitters may review their own change sets (single review mode). */
  selfReview: boolean;
}

function ElementsLoaded({ changeSet, own, selfReview }: ElementsLoadedProps) {
  const { i18n } = useTranslation();
  // Deleted elements too: restore items point to them.
  const elements = useElements(changeSet.ontologyId, { status: 'all' });
  return (
    <QueryState query={elements} loading={<LoadingState variant="detail" />}>
      {(list) => (
        <ChangeSetReview changeSet={changeSet} elements={list} language={i18n.resolvedLanguage ?? i18n.language} own={own} selfReview={selfReview} />
      )}
    </QueryState>
  );
}

interface ChangeSetReviewProps extends ElementsLoadedProps {
  elements: readonly Element[];
  language: string;
}

function ChangeSetReview({ changeSet, elements, language, own, selfReview }: ChangeSetReviewProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const permissions = usePermissions();
  // In separate review mode nobody reviews what they submitted (403 `changeset.self_review`).
  const blockedAsSubmitter = own && !selfReview;
  const canReview = permissions.canReview && !blockedAsSubmitter;
  const [withdrawing, setWithdrawing] = useState(false);
  const [mergingSame, setMergingSame] = useState(false);
  const pendingHintId = useId();
  const wide = useMediaQuery(DESKTOP_QUERY);
  const evidencePanelId = useId();

  const context = useMemo(() => buildRefContext(changeSet.items, elements, language), [changeSet.items, elements, language]);
  const groups = ELEMENT_KINDS.map((kind) => ({
    kind,
    items: changeSet.items.filter((item) => item.kind === kind).sort((a, b) => a.seq - b.seq),
  })).filter((group) => group.items.length > 0);
  const ordered = groups.flatMap((group) => group.items);
  // Items are paged in the order they are listed, across the kind groups.
  const pager = usePagination(ordered.length, changeSet.id);
  const pageItems = ordered.slice(pager.start, pager.end);
  const onPage = new Set(pageItems);
  const pageGroups = groups.map((group) => ({ ...group, shown: group.items.filter((item) => onPage.has(item)) })).filter((group) => group.shown.length > 0);
  const listRef = useRef<HTMLDivElement>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<ChangeItem | null>(null);
  const [mergeResult, setMergeResult] = useState<MergeResult | null>(null);
  // The evidence beside the list follows the page: the first item of it until one is chosen there.
  const selected = pageItems.find((item) => item.id === selectedId) ?? pageItems[0];

  const isOpen = changeSet.status === 'open';
  const canDecide = canReview && isOpen;
  // Submitters can take their open change set back in either review mode, reviewers too (spec 002, section 8).
  const canWithdraw = isOpen && own;
  const withdrawButton = canWithdraw ? (
    <Button variant="secondary" className="text-error-strong" onClick={() => setWithdrawing(true)}>
      <Undo2 aria-hidden />
      {t('review.withdraw')}
    </Button>
  ) : null;
  const isAi = isAiSource(changeSet.source);
  const pending = changeSet.items.filter((item) => item.decision === 'pending');
  const pendingCount = pending.length;
  // AI proposals are bulk-accepted only when confident; imports and manual edits as a whole.
  const bulkItems = acceptsAll(changeSet.source) ? pending : isAi ? highConfidencePending(changeSet.items) : [];
  // Items recorded as concepts already there are accepted on their own, after a list (spec 004, 5.4).
  const sameConceptItems = changeSet.source === 'ai_extraction' ? sameConceptPending(changeSet.items) : [];

  const refreshDetail = () => queryClient.invalidateQueries({ queryKey: changeSetKeys.detail(changeSet.id) });
  const markListStale = () => queryClient.invalidateQueries({ queryKey: [...changeSetKeys.all, 'list'], refetchType: 'none' });

  const applyItem = (item: ChangeItem) => {
    replaceItemInCache(queryClient, changeSet.id, item);
    void refreshDetail();
    void markListStale();
  };

  const decide = useMutation({
    mutationFn: ({ itemId, patch }: { itemId: string; patch: ItemPatch }) => patchItem(changeSet.id, itemId, patch),
    onSuccess: applyItem,
    onError: (error) => toast.error(t('review.decideFailed'), message(error)),
  });

  const bulk = useMutation({
    mutationFn: (itemIds: string[]) => decideItems(changeSet.id, itemIds, 'accepted'),
    onSuccess: async (_, itemIds) => {
      toast.success(t(isAi ? 'review.bulkAccepted' : 'review.allAccepted', { count: itemIds.length }));
      await Promise.all([refreshDetail(), markListStale()]);
    },
    onError: (error) => toast.error(t('review.decideFailed'), message(error)),
  });

  const merge = useMutation({
    mutationFn: () => mergeChangeSet(changeSet.id, changeSet.resolutionToken),
    // Another change set was merged since the page loaded: show what the merge would do now.
    onError: (error) => (isResolutionChanged(error) ? refreshDetail() : undefined),
    onSuccess: async (result) => {
      setMergeResult(result);
      toast.success(t('review.mergedToast', { count: result.applied }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: changeSetKeys.all }),
        queryClient.invalidateQueries({ queryKey: ontologyKeys.all }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ]);
    },
  });

  const busyItemId = decide.isPending ? decide.variables?.itemId : undefined;

  return (
    <>
      <BackToList ontologyId={changeSet.ontologyId} />
      <PageHeader
        title={changeSet.title}
        info={t('review.detailInfo')}
        actions={
          canDecide ? (
            <>
              {pendingCount > 0 ? (
                <span id={pendingHintId} className="text-sm text-muted-foreground">
                  {t('review.pendingHint', { count: pendingCount })}
                </span>
              ) : null}
              {bulkItems.length > 0 ? (
                <Button variant="secondary" loading={bulk.isPending} onClick={() => bulk.mutate(bulkItems.map((item) => item.id))}>
                  {bulk.isPending ? null : <CheckCheck aria-hidden />}
                  {t(isAi ? 'review.acceptHighConfidence' : 'review.acceptAll', { count: bulkItems.length })}
                </Button>
              ) : null}
              {sameConceptItems.length > 0 ? (
                <Button variant="secondary" disabled={bulk.isPending} onClick={() => setMergingSame(true)}>
                  <Combine aria-hidden />
                  {t('review.matchBulk.button', { count: sameConceptItems.length })}
                </Button>
              ) : null}
              <Button
                disabled={pendingCount > 0}
                loading={merge.isPending}
                aria-describedby={pendingCount > 0 ? pendingHintId : undefined}
                onClick={() => merge.mutate()}
              >
                {merge.isPending ? null : <GitMerge aria-hidden />}
                {t('review.merge')}
              </Button>
              {withdrawButton}
            </>
          ) : (
            <>
              {isOpen ? (
                <span className="inline-flex items-center gap-0.5">
                  <Badge tone="neutral">{t('review.readOnly')}</Badge>
                  <InfoTip label={t('review.readOnly')}>
                    {permissions.canReview && blockedAsSubmitter
                      ? t('review.selfReviewNotice')
                      : t('review.readOnlyNotice', { role: t('user.roles.reviewer') })}
                  </InfoTip>
                </span>
              ) : null}
              <Badge tone={changeSet.status === 'merged' ? 'success' : changeSet.status === 'rejected' ? 'neutral' : 'warning'}>
                {t(`review.status.${changeSet.status}`)}
              </Badge>
              {changeSet.status === 'merged' ? (
                <Link to="/ontology" search={{ ontology: changeSet.ontologyId }} className={buttonVariants({ variant: 'secondary' })}>
                  <Network aria-hidden />
                  {t('review.viewOntology')}
                </Link>
              ) : null}
              {withdrawButton}
            </>
          )
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
        <span className="inline-flex min-w-0 items-center gap-1.5">
          {t('review.sourceLabel')}
          <SourceBadge source={changeSet.source} />
          {changeSet.documentId ? (
            <span className="min-w-0 max-w-72 font-medium text-foreground">
              <DocumentName id={changeSet.documentId} />
            </span>
          ) : null}
        </span>
        <span className="tabular-nums">{t('review.countsSummary', { ...changeSet.counts })}</span>
      </div>

      <div className="space-y-4">
        {mergeResult ? <MergeResultNotice result={mergeResult} items={changeSet.items} context={context} /> : null}
        {merge.isError && isResolutionChanged(merge.error) ? (
          <InlineNotice tone="warning" title={t('review.resolutionChangedTitle')}>
            {t('review.resolutionChangedDescription')}
          </InlineNotice>
        ) : merge.isError ? (
          <ErrorState error={merge.error} title={t('review.mergeFailedTitle')} onRetry={canDecide ? () => merge.mutate() : undefined} />
        ) : null}
      </div>

      {ordered.length === 0 ? (
        <Card className="mt-4">
          <CardContent className="text-sm text-muted-foreground">{t('review.noItems')}</CardContent>
        </Card>
      ) : (
        // Columns follow `wide`, not a CSS breakpoint: rem breakpoints move with the browser font
        // size, and the evidence panel's placement must match the layout. Only AI proposals have
        // evidence; imports and manual edits get the list alone.
        <div className={cn('mt-4 grid items-start gap-6', wide && isAi ? 'grid-cols-[minmax(0,1fr)_minmax(0,26rem)]' : 'max-w-4xl')}>
          <div ref={listRef} className="space-y-6">
            {pageGroups.map((group) => (
              <section key={group.kind} aria-labelledby={`group-${group.kind}`} className="space-y-3">
                <h2 id={`group-${group.kind}`} className="flex items-center gap-2 text-base font-semibold text-foreground">
                  {t(`kinds.${group.kind}`)}
                  <Badge tone="neutral" className="tabular-nums">
                    {group.items.length}
                  </Badge>
                </h2>
                {group.shown.map((item) => (
                  <Fragment key={item.id}>
                    <ChangeItemCard
                      item={item}
                      changeSetId={changeSet.id}
                      context={context}
                      isAi={isAi}
                      selected={isAi && (wide ? item.id === selected?.id : item.id === selectedId)}
                      onSelect={() => setSelectedId((current) => (!wide && current === item.id ? null : item.id))}
                      evidencePanelId={wide ? undefined : evidencePanelId}
                      canDecide={canDecide}
                      busy={busyItemId === item.id || bulk.isPending || merge.isPending}
                      onDecide={(decision) => decide.mutate({ itemId: item.id, patch: { decision } })}
                      onDecideMatch={(matchDecision) => decide.mutate({ itemId: item.id, patch: { matchDecision } })}
                      onEdit={() => setEditing(item)}
                      impactOntologyId={isOpen ? changeSet.ontologyId : undefined}
                    />
                    {/* Stacked layout: the evidence opens under the chosen item, not after the whole list. */}
                    {isAi && !wide && item.id === selectedId ? <EvidencePanel id={evidencePanelId} item={item} context={context} inline /> : null}
                  </Fragment>
                ))}
              </section>
            ))}
            <Pagination state={pager} total={ordered.length} className="rounded-xl border" onChange={() => listRef.current?.scrollIntoView({ block: 'start' })} />
          </div>
          {isAi && wide && selected ? <EvidencePanel key={selected.id} item={selected} context={context} /> : null}
        </div>
      )}

      {canDecide ? (
        <SameConceptDialog changeSet={changeSet} items={sameConceptItems} context={context} open={mergingSame && sameConceptItems.length > 0} onOpenChange={setMergingSame} />
      ) : null}

      {canWithdraw ? <WithdrawDialog changeSet={changeSet} open={withdrawing} onOpenChange={setWithdrawing} /> : null}

      {canDecide ? (
        <ChangeItemEditDialog
          changeSetId={changeSet.id}
          item={editing}
          items={changeSet.items}
          context={context}
          onClose={() => setEditing(null)}
          onSaved={(item) => {
            applyItem(item);
            setEditing(null);
            toast.success(t('review.edit.saved'));
          }}
        />
      ) : null}
    </>
  );
}

function isResolutionChanged(error: unknown): boolean {
  return isApiError(error) && error.code === 'changeset.resolution_changed';
}

interface WithdrawDialogProps {
  changeSet: ChangeSetDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Confirms withdrawing a change set the user submitted: it is rejected as a whole and cannot be reopened. */
function WithdrawDialog({ changeSet, open, onOpenChange }: WithdrawDialogProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const withdraw = useMutation({
    mutationFn: () => rejectChangeSet(changeSet.id),
    onSuccess: async () => {
      onOpenChange(false);
      toast.success(t('review.withdrawn'));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: changeSetKeys.all }),
        queryClient.invalidateQueries({ queryKey: ontologyKeys.list() }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ]);
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) withdraw.reset();
        onOpenChange(next);
      }}
    >
      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('review.withdrawTitle', { title: changeSet.title })}</DialogTitle>
        <DialogDescription>{t('review.withdrawDescription')}</DialogDescription>
        <div className="mt-5 space-y-4">
          {withdraw.isError ? (
            <InlineNotice tone="error" title={t('review.withdrawFailedTitle')}>
              {message(withdraw.error)}
            </InlineNotice>
          ) : null}
          <div className="flex justify-end gap-2">
            <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
            <Button variant="destructive" loading={withdraw.isPending} onClick={() => withdraw.mutate()}>
              {withdraw.isPending ? null : <Undo2 aria-hidden />}
              {t('review.withdrawConfirm')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface SameConceptDialogProps {
  changeSet: ChangeSetDetail;
  items: readonly (ChangeItem & { match: ItemMatch })[];
  context: RefContext;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Lists where each same-concept item goes, then accepts them together once the reviewer confirms. */
function SameConceptDialog({ changeSet, items, context, open, onOpenChange }: SameConceptDialogProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const accept = useMutation({
    mutationFn: (itemIds: string[]) => decideItems(changeSet.id, itemIds, 'accepted'),
    onSuccess: async (_, itemIds) => {
      onOpenChange(false);
      toast.success(t('review.matchBulk.accepted', { count: itemIds.length }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: changeSetKeys.detail(changeSet.id) }),
        queryClient.invalidateQueries({ queryKey: [...changeSetKeys.all, 'list'], refetchType: 'none' }),
      ]);
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) accept.reset();
        onOpenChange(next);
      }}
    >
      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('review.matchBulk.title')}</DialogTitle>
        <DialogDescription>{t('review.matchBulk.description')}</DialogDescription>
        <div className="mt-5 space-y-4">
          <ul className="max-h-72 space-y-1.5 overflow-y-auto text-sm">
            {items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-x-1.5">
                <span className="font-medium text-foreground">{itemLabel(item, context)}</span>
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                <span className="sr-only">{t('review.matchBulk.into')}</span>
                <span className="font-medium text-foreground">{item.match.label}</span>
                <span className="text-muted-foreground">
                  {t('review.matchBulk.place', {
                    place: t(`review.matchBulk.places.${matchPlace(item.match, changeSet.id)}`, { title: item.match.changeSetTitle ?? '' }),
                  })}
                </span>
              </li>
            ))}
          </ul>
          {accept.isError ? (
            <InlineNotice tone="error" title={t('review.matchBulk.failedTitle')}>
              {message(accept.error)}
            </InlineNotice>
          ) : null}
          <div className="flex justify-end gap-2">
            <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
            <Button loading={accept.isPending} onClick={() => accept.mutate(items.map((item) => item.id))}>
              {accept.isPending ? null : <CheckCheck aria-hidden />}
              {t('review.matchBulk.confirm', { count: items.length })}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface EvidencePanelProps {
  id?: string;
  item: ChangeItem;
  context: RefContext;
  /** Opened under the chosen item (stacked layout) rather than beside the list. */
  inline?: boolean;
}

function EvidencePanel({ id, item, context, inline = false }: EvidencePanelProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const current = item.evidence[index] ?? item.evidence[0];
  useEffect(() => {
    if (inline) ref.current?.scrollIntoView({ block: 'nearest' });
  }, [inline]);
  return (
    <Card id={id} ref={ref} role="region" className={inline ? undefined : 'sticky top-6'} aria-labelledby={titleId}>
      <CardHeader>
        <CardTitle id={titleId} className="flex items-center gap-2">
          <Quote className="size-4 text-info-strong" aria-hidden />
          {t('review.evidenceTitle')}
        </CardTitle>
        <p className="truncate text-sm text-muted-foreground">{itemLabel(item, context)}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {item.evidence.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('review.noEvidence')}</p>
        ) : (
          <>
            {item.evidence.length > 1 ? (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('review.evidenceSwitch')}>
                {item.evidence.map((evidence, position) => (
                  <Button
                    key={evidence.id}
                    variant="ghost"
                    size="sm"
                    aria-pressed={position === index}
                    onClick={() => setIndex(position)}
                    className={cn('aria-pressed:bg-primary-soft aria-pressed:text-primary-strong')}
                  >
                    {t('review.evidenceN', { n: position + 1 })}
                  </Button>
                ))}
              </div>
            ) : null}
            {current ? <EvidenceExcerpt key={current.id} evidence={current} /> : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function MergeResultNotice({ result, items, context }: { result: MergeResult; items: readonly ChangeItem[]; context: RefContext }) {
  const { t, i18n } = useTranslation();
  const byId = new Map(items.map((item) => [item.id, item]));
  if (result.skipped.length === 0) {
    return (
      <InlineNotice tone="success" title={t('review.mergedTitle')}>
        {t('review.mergedDescription', { count: result.applied })}
      </InlineNotice>
    );
  }
  return (
    <InlineNotice tone="warning" title={t('review.mergedWithSkipsTitle', { skipped: result.skipped.length })}>
      <p>{t('review.mergedWithSkipsDescription', { applied: result.applied, skipped: result.skipped.length })}</p>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
        {result.skipped.map((skip) => {
          const item = byId.get(skip.itemId);
          return (
            <li key={skip.itemId}>
              <span className="font-medium">{item ? itemLabel(item, context) : t('review.unknownItem')}</span>
              {t('common.colon')}
              {codeMessage(i18n, skip.code)}
            </li>
          );
        })}
      </ul>
    </InlineNotice>
  );
}
