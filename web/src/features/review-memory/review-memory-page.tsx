import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Brain, SearchX } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError, isForbidden } from '@/api/errors';
import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { ErrorState } from '@/components/states/error-state';
import { ForbiddenState } from '@/components/states/forbidden-state';
import { LoadingState } from '@/components/states/loading-state';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePermissions } from '@/features/auth/permissions';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import type { OntologySummary } from '@/features/ontologies/api';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';
import { formatDateTime, formatRecent } from '@/lib/format';

import { clearMemory, deleteMemory, memoryKeys, restoreMemory, useReviewMemory, type MemoryEntry, type MemoryKind } from './api';

interface Props {
  ontologyId?: string;
  kind?: MemoryKind;
  q?: string;
  entry?: string;
  onSearchChange: (change: { ontology?: string; kind?: MemoryKind; q?: string; entry?: string }) => void;
}

export function ReviewMemoryPage({ ontologyId, kind, q, entry, onSearchChange }: Props) {
  const { t } = useTranslation('translation', { keyPrefix: 'reviewMemory' });
  const { query, ontologies, selected } = useSelectedOntology(ontologyId);
  const canManage = usePermissions().canReview;
  const [searchText, setSearchText] = useState(q ?? '');
  useEffect(() => {
    const timeout = window.setTimeout(() => setSearchText(q ?? ''), 0);
    return () => window.clearTimeout(timeout);
  }, [q]);
  useEffect(() => {
    if (searchText === (q ?? '')) return;
    const timeout = window.setTimeout(() => onSearchChange({ q: searchText || undefined, entry: undefined }), 300);
    return () => window.clearTimeout(timeout);
  }, [searchText, q, onSearchChange]);
  return <>
    {query.isPending || query.isError || !selected || !ontologies ? <>
      <PageHeader title={t('title')} />
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        : <Card><EmptyState icon={Brain} title={t('noOntology')} /></Card>}
    </> : <MemoryContent key={selected.id} ontologyId={selected.id} ontologies={ontologies} kind={kind} q={q} entry={entry} searchText={searchText}
        onSearchText={setSearchText} onSearchChange={onSearchChange} canManage={canManage} />}
  </>;
}

function MemoryContent({ ontologyId, ontologies, kind, q, entry, searchText, onSearchText, onSearchChange, canManage }: {
  ontologyId: string; kind?: MemoryKind; q?: string; entry?: string; searchText: string;
  onSearchText: (text: string) => void; onSearchChange: Props['onSearchChange']; canManage: boolean;
  ontologies: readonly OntologySummary[];
}) {
  const { t, i18n } = useTranslation('translation', { keyPrefix: 'reviewMemory' });
  const common = useTranslation().t;
  const toast = useToast();
  const message = useErrorMessage();
  const queryClient = useQueryClient();
  const query = useReviewMemory(ontologyId, kind, q);
  const pages = query.data?.pages ?? [];
  const total = pages[0]?.total ?? 0;
  const max = pages[0]?.max ?? 0;
  const items = pages.flatMap((page) => page.items);
  const [confirmClear, onConfirmClear] = useState(false);
  const highlighted = useRef<HTMLTableRowElement>(null);
  useEffect(() => highlighted.current?.scrollIntoView?.({ block: 'nearest' }), [entry, items.length]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: memoryKeys.all });
  const restore = useMutation({
    mutationFn: (id: string) => restoreMemory(ontologyId, id),
    onSuccess: () => void refresh(),
    onError: (error) => toast.error(isApiError(error) && error.code === 'review_memory.not_restorable' ? t('notRestorable')
      : isForbidden(error) ? t('forbiddenAction') : t('restoreFailed'), message(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteMemory(ontologyId, id),
    onSuccess: async (_, id) => {
      await refresh();
      toast.success(t('deleted'), undefined, { label: t('undo'), onClick: () => window.setTimeout(() => restore.mutate(id), 0) });
    },
    onError: (error) => toast.error(isForbidden(error) ? t('forbiddenAction') : t('deleteFailed'), message(error)),
  });
  const clear = useMutation({
    mutationFn: () => clearMemory(ontologyId),
    onSuccess: async (result) => { onConfirmClear(false); await refresh(); toast.success(t('cleared', { count: result.cleared })); },
    onError: (error) => toast.error(isForbidden(error) ? t('forbiddenAction') : t('clearFailed'), message(error)),
  });

  return <>
    <PageHeader title={t('title')} actions={<div className="flex items-center gap-3">
      <OntologySelector ontologies={ontologies} value={ontologyId}
        onValueChange={(ontology) => onSearchChange({ ontology, kind: undefined, q: undefined, entry: undefined })} />
      {canManage ? <Button variant="destructive" disabled={total === 0} onClick={() => onConfirmClear(true)}>{t('clear')}</Button> : null}
    </div>} />
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <p>{t('description')}</p><span className="tabular-nums">{t('count', { total, max })}</span>
    </div>
    <div className="mb-4 flex flex-wrap gap-3">
      <label className="text-sm text-muted-foreground">{t('kindFilter')}
        <NativeSelect value={kind ?? ''} onChange={(event) => onSearchChange({ kind: event.target.value as MemoryKind || undefined, entry: undefined })} containerClassName="mt-1 w-48">
          <option value="">{t('all')}</option><option value="rejected">{t('kinds.rejected')}</option>
          <option value="renamed">{t('kinds.renamed')}</option><option value="kept_apart">{t('kinds.kept_apart')}</option>
        </NativeSelect>
      </label>
      <label className="text-sm text-muted-foreground">{t('search')}
        <Input value={searchText} maxLength={100} onChange={(event) => onSearchText(event.target.value)} className="mt-1 w-64" />
      </label>
    </div>
    {query.isPending ? <LoadingState /> : query.isError ? isForbidden(query.error) ? <ForbiddenState requiredRole="viewer" />
      : <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      : items.length === 0 ? <Card><EmptyState icon={kind || q ? SearchX : Brain}
        title={t(kind || q ? 'noResultsTitle' : 'emptyTitle')}
        description={kind || q ? t('noResultsDescription') : t('emptyDescription')}
        action={kind || q ? <Button onClick={() => { onSearchText(''); onSearchChange({ kind: undefined, q: undefined, entry: undefined }); }}>{t('clearFilters')}</Button>
          : <Link to="/review" search={{ ontology: ontologyId }} className={buttonVariants()}>{t('goReview')}</Link>} /></Card>
      : <Card><Table aria-label={t('tableLabel')}><TableHeader><TableRow>
        {(['kind', 'elementKind', 'content', 'reason', 'source', 'decidedBy', 'time', 'hits'] as const).map((column) => <TableHead key={column} numeric={column === 'hits'}>{t(`columns.${column}`)}</TableHead>)}
        {canManage ? <TableHead>{t('columns.actions')}</TableHead> : null}
      </TableRow></TableHeader><TableBody>
        {items.map((item) => <TableRow key={item.id} ref={item.id === entry ? highlighted : undefined} aria-current={item.id === entry ? 'true' : undefined}
          className={cn(item.id === entry && 'bg-primary-soft')}>
          <TableCell><Badge tone="neutral">{t(`kinds.${item.kind}`)}</Badge></TableCell>
          <TableCell>{common(`kinds.${item.elementKind}`)}</TableCell>
          <TableCell>{content(item)}</TableCell>
          <TableCell>{item.detail.kind === 'rejected' && item.detail.reason ? common(`review.rejectReasons.${item.detail.reason}`) : '—'}</TableCell>
          <TableCell>{item.sourceChangeSetId ? <Link to="/review/$changeSetId" params={{ changeSetId: item.sourceChangeSetId }} className="text-primary-strong hover:underline">{t('viewSource')}</Link> : '—'}</TableCell>
          <TableCell>{item.decidedByName ?? '—'}</TableCell>
          <TableCell><time dateTime={item.createdAt} title={formatDateTime(item.createdAt, i18n.language)}>{formatRecent(item.createdAt, i18n.language)}</time></TableCell>
          <TableCell numeric>{item.hits}</TableCell>
          {canManage ? <TableCell><Button variant="ghost" size="sm" disabled={remove.isPending} onClick={() => remove.mutate(item.id)}>{t('delete')}</Button></TableCell> : null}
        </TableRow>)}
      </TableBody></Table>
        {query.hasNextPage ? <div className="p-4"><Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{t('loadMore')}</Button></div> : null}
      </Card>}
    <Dialog open={confirmClear} onOpenChange={onConfirmClear}><DialogContent closeLabel={common('common.close')}>
      <DialogTitle>{t('clearTitle')}</DialogTitle><DialogDescription>{t('clearDescription', { count: total })}</DialogDescription>
      <div className="mt-5 flex justify-end gap-2"><DialogClose className={buttonVariants({ variant: 'secondary' })}>{common('common.cancel')}</DialogClose>
        <Button variant="destructive" loading={clear.isPending} onClick={() => clear.mutate()}>{t('clear')}</Button></div>
    </DialogContent></Dialog>
  </>;
}

function content(item: MemoryEntry) {
  if (item.detail.kind === 'renamed') return `${item.label} → ${item.detail.toLabelZh}`;
  if (item.detail.kind === 'kept_apart') return `${item.label} ↔ ${item.detail.otherLabel}`;
  return item.label;
}
