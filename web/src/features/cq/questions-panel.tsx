import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Ellipsis, ListChecks } from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { useToast } from '@/components/feedback/toast';
import { EmptyState } from '@/components/states/empty-state';
import { ErrorState } from '@/components/states/error-state';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Pagination } from '@/components/ui/pagination';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { elementName, useElements } from '@/features/ontologies/api';
import { useComparison } from '@/features/releases/api';
import { usePagination } from '@/lib/pagination';

import { archiveQuestion, checkAll, checkQuestion, importQuestions, listKey, patchQuestion, useCoverage, useQuestions, type Question } from './api';
import { CheckResult } from './check-result';
import { cqMessage } from './error-message';
import { QuestionDialog } from './question-dialog';

interface Props {
  ontologyId: string;
  releaseId?: string | null;
  canEdit: boolean;
}

export function QuestionsPanel({ ontologyId, releaseId = null, canEdit }: Props) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuestions(ontologyId, true);
  const coverage = useCoverage(ontologyId, releaseId, query.data?.items);
  const items = query.data?.items ?? [];
  const pager = usePagination(items.length);
  const picker = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<Question | 'new' | null>(null);
  const [archiving, setArchiving] = useState<Question | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const needsTypes = editing !== null || items.some((item) => item.expect.kind === 'objects');
  const working = useElements(needsTypes ? ontologyId : undefined, { kind: 'entity_type' });
  // A type removed from the working version can still be expected on the active release.
  const changes = useComparison(ontologyId, needsTypes && releaseId ? releaseId : undefined);
  const typeNames = new Map<string, string>();
  for (const change of changes.data?.changes ?? []) {
    if (change.kind === 'entity_type' && change.change === 'removed') typeNames.set(change.elementId, change.label);
  }
  for (const element of working.data ?? []) {
    if (element.kind === 'entity_type') typeNames.set(element.id, elementName(element, i18n.language));
  }

  const refresh = () => client.invalidateQueries({ queryKey: listKey(ontologyId) });
  const action = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onMutate: () => setError(null),
    onSuccess: refresh,
    onError: (cause) => { setError(cause); void refresh(); },
  });
  const bulk = useMutation({
    mutationFn: () => checkAll(ontologyId),
    onMutate: () => setError(null),
    onSuccess: refresh,
    onError: async (cause) => {
      setError(cause);
      await refresh();
    },
  });
  const running = query.data?.running ?? items.some(({ lastCheck }) => lastCheck?.result === 'pending'
    && bulk.data?.checks.some((check) => check.id === lastCheck.id));
  const busy = bulk.isPending || running;
  const writeControls = <>
    <Button variant="secondary" disabled={action.isPending} onClick={() => picker.current?.click()}>{t('cq.import')}</Button>
    <Button onClick={() => { setError(null); setEditing('new'); }}>{t('cq.create')}</Button>
  </>;

  const affected = (coverage.data?.items ?? []).flatMap((item) => {
    if (item.status !== 'element_missing' && item.status !== 'binding_missing') return [];
    const question = items.find((q) => q.id === item.questionId);
    if (!question) return [];
    const missing = item.elements.filter((el) => !el.present || !el.bound).map((el) => el.label);
    return [<li key={question.id}><strong>{question.text}</strong> {t(`cq.coverage.${item.status}`)} {missing.join(t('common.listSeparator'))}</li>];
  });
  const expectation = ({ expect }: Question) => {
    if (expect.kind === 'number') return t('cq.numberRange', { value: expect.number, tolerance: expect.tolerance });
    if (expect.kind === 'objects') return t('cq.objectCount', { count: expect.keys.length, type: typeNames.get(expect.typeId ?? '') ?? t('review.unknownType') });
    return t('cq.kinds.answerable');
  };

  const refreshEdit = async () => {
    if (!editing || editing === 'new') return;
    const result = await query.refetch();
    if (result.isSuccess) setEditing(result.data.items.find((item) => item.id === editing.id) ?? null);
  };
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>{t('cq.title')}</CardTitle>
        {canEdit && <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={busy || !items.length} onClick={() => bulk.mutate()}>
            {t(busy ? 'cq.checkingAll' : 'cq.checkAll')}
          </Button>
          {writeControls}
        </div>}
      </CardHeader>
      <CardContent className="space-y-4">
        {canEdit && <input ref={picker} type="file" hidden accept=".toml" aria-label={t('cq.importFile')} onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          e.currentTarget.value = '';
          if (file) action.mutate(async () => {
            const result = await importQuestions(ontologyId, file);
            toast.success(t('cq.importResult', result));
          });
        }} />}
        {error !== null && <InlineNotice tone="error">{cqMessage(i18n, error)}</InlineNotice>}
        {items.length > 0 && coverage.error && <ErrorState error={coverage.error} onRetry={() => void coverage.refetch()} />}
        {affected.length > 0 && <InlineNotice tone="warning" title={t('cq.coverage.title')}><ul>{affected}</ul></InlineNotice>}
        <QueryState query={query}>
          {() => items.length === 0 ? <EmptyState icon={ListChecks} title={t('cq.emptyTitle')} description={t('cq.empty')}
            action={canEdit && <div className="flex gap-2">{writeControls}</div>} /> : <>
            <Table aria-label={t('cq.title')}>
              <TableHeader><TableRow>
                <TableHead>{t('cq.text')}</TableHead>
                <TableHead>{t('cq.expectation')}</TableHead>
                <TableHead>{t('cq.lastCheck')}</TableHead>
                {canEdit && <TableHead>{t('ontologyPage.list.columns.actions')}</TableHead>}
              </TableRow></TableHeader>
              <TableBody>{items.slice(pager.start, pager.end).map((q, index) => {
                const position = pager.start + index;
                const move = (neighbor: Question | undefined) => {
                  if (neighbor) action.mutate(() => patchQuestion(q.id, { revision: q.revision, position: neighbor.position }));
                };
                return <TableRow key={q.id}>
                  <TableCell className="max-w-md break-words font-medium">{q.text}</TableCell>
                  <TableCell>{expectation(q)}</TableCell>
                  <TableCell><CheckResult check={q.lastCheck} /></TableCell>
                  {canEdit && <TableCell><div className="flex items-center gap-1">
                    <Button size="sm" variant="secondary" disabled={action.isPending || q.lastCheck?.result === 'pending'}
                      onClick={() => action.mutate(() => checkQuestion(q.id))}>{t('cq.check')}</Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger disabled={action.isPending} aria-label={t('ontologyPage.moreActions')}
                        title={t('ontologyPage.moreActions')} className={buttonVariants({ variant: 'ghost', size: 'icon-sm' })}>
                        <Ellipsis aria-hidden />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem onClick={() => { setError(null); setEditing(q); }}>{t('cq.edit')}</DropdownMenuItem>
                        <DropdownMenuItem disabled={position === 0} onClick={() => move(items[position - 1])}>{t('cq.moveUp')}</DropdownMenuItem>
                        <DropdownMenuItem disabled={position + 1 === items.length} onClick={() => move(items[position + 1])}>{t('cq.moveDown')}</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setArchiving(q)}>{t('cq.archive')}</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div></TableCell>}
                </TableRow>;
              })}</TableBody>
            </Table>
            <Pagination state={pager} total={items.length} />
          </>}
        </QueryState>
      </CardContent>
      {canEdit && editing && <QuestionDialog key={editing === 'new' ? 'new' : `${editing.id}-${editing.revision}`}
        ontologyId={ontologyId} question={editing === 'new' ? null : editing} types={typeNames} typeError={working.error ?? changes.error}
        retryTypes={() => { void working.refetch(); if (releaseId) void changes.refetch(); }}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void refresh(); }} onRefresh={() => void refreshEdit()} />}
      {canEdit && archiving && <Dialog open onOpenChange={(open) => { if (!open) setArchiving(null); }}>
        <DialogContent closeLabel={t('common.close')}>
          <DialogTitle>{t('cq.archive')}</DialogTitle>
          <DialogDescription>{t('cq.archiveConfirm', { text: archiving.text })}</DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setArchiving(null)}>{t('common.cancel')}</Button>
            <Button onClick={() => {
              action.mutate(() => archiveQuestion(archiving));
              setArchiving(null);
            }}>{t('cq.archive')}</Button>
          </div>
        </DialogContent>
      </Dialog>}
    </Card>
  );
}
