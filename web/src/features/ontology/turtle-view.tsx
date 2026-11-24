import { useMutation } from '@tanstack/react-query';
import { useBlocker } from '@tanstack/react-router';
import { Crosshair, GitPullRequestArrow, Pencil } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { TurtleEditor, type TurtleEditorHandle } from '@/components/code/turtle-editor';
import { InfoTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { usePermissions } from '@/features/auth/permissions';
import { saveTurtle, useOntologyTurtle, type ImportResult, type OntologySummary } from '@/features/ontologies/api';
import { ImportResultView, useRefreshAfterImport } from '@/features/ontologies/import-owl';
import { useErrorMessage } from '@/i18n/error-message';

const EDITOR_SIZE = 'h-[min(65dvh,40rem)] min-h-80';

/** 422 `import.parse_error`: the line the server names (null when it does not know), else undefined. */
function parseErrorLine(error: unknown): number | null | undefined {
  if (!isApiError(error) || error.code !== 'import.parse_error') return undefined;
  return typeof error.body.line === 'number' ? error.body.line : null;
}

/**
 * Expert mode (spec 002, section 7): the working version's Turtle export, read-only by default.
 * Edited Turtle is compared with the working version on the server and always becomes a change
 * set for review, never a direct change.
 */
export function TurtleView({ ontology }: { ontology: OntologySummary }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { canUpload } = usePermissions();
  const refresh = useRefreshAfterImport();
  const query = useOntologyTurtle(ontology.id);
  const editor = useRef<TurtleEditorHandle>(null);
  const errorId = useId();
  // The export the edit started from; null while only reading.
  const [base, setBase] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [check, setCheck] = useState<'empty' | 'unchanged' | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const editing = base !== null;
  const dirty = editing && draft !== base;

  const generate = useMutation({
    mutationFn: (turtle: string) => saveTurtle(ontology.id, turtle),
    onSuccess: async (imported) => {
      setBase(null);
      setResult(imported);
      await refresh();
    },
    onError: (error) => {
      const line = parseErrorLine(error);
      if (typeof line === 'number') editor.current?.revealLine(line);
    },
  });

  // Switching views, ontologies or pages with unsaved edits asks first; so does closing the tab.
  const blocker = useBlocker({ shouldBlockFn: () => true, disabled: !dirty, withResolver: true });

  const startEditing = (text: string) => {
    setBase(text);
    setDraft(text);
    setCheck(null);
    generate.reset();
    editor.current?.focus();
  };

  const cancel = () => {
    setBase(null);
    setCheck(null);
    generate.reset();
  };

  const submit = () => {
    if (draft.trim() === '') {
      setCheck('empty');
      return;
    }
    if (draft === base) {
      setCheck('unchanged');
      return;
    }
    setCheck(null);
    generate.mutate(draft);
  };

  const errorLine = generate.isError ? parseErrorLine(generate.error) : undefined;
  const title = t('ontologyPage.turtle.title');

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border p-4">
          <div className="flex min-w-0 items-center gap-1">
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
            <InfoTip label={t('common.aboutPage', { title })}>{t('ontologyPage.turtle.info')}</InfoTip>
          </div>
          {canUpload && query.isSuccess ? (
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              {editing ? (
                <>
                  <span className="text-xs text-muted-foreground">{t('ontologyPage.turtle.reviewNote')}</span>
                  <Button variant="secondary" disabled={generate.isPending} onClick={cancel}>
                    {t('common.cancel')}
                  </Button>
                  <Button loading={generate.isPending} onClick={submit}>
                    {generate.isPending ? null : <GitPullRequestArrow aria-hidden />}
                    {t('ontologyPage.turtle.generate')}
                  </Button>
                </>
              ) : (
                <Button variant="secondary" onClick={() => startEditing(query.data)}>
                  <Pencil aria-hidden />
                  {t('ontologyPage.edit.edit')}
                </Button>
              )}
            </div>
          ) : null}
        </div>

        <div className="space-y-3 p-4">
          <QueryState query={query} loading={<Skeleton className={`rounded-lg ${EDITOR_SIZE}`} />}>
            {(text) => (
              <>
                {editing && text !== base ? (
                  <InlineNotice tone="warning" title={t('ontologyPage.turtle.baseChangedTitle')}>
                    {t('ontologyPage.turtle.baseChangedDescription')}
                  </InlineNotice>
                ) : null}
                {check === 'empty' ? <InlineNotice tone="error">{t('ontologyPage.turtle.emptyDraft')}</InlineNotice> : null}
                {check === 'unchanged' ? <InlineNotice tone="info">{t('ontologyPage.form.nothingChanged')}</InlineNotice> : null}
                {generate.isError ? (
                  <div id={errorId}>
                    {errorLine !== undefined ? (
                      <InlineNotice
                        tone="error"
                        title={t('ontologyPage.turtle.parseErrorTitle')}
                        action={
                          errorLine !== null ? (
                            <Button variant="secondary" size="sm" onClick={() => editor.current?.revealLine(errorLine)}>
                              <Crosshair aria-hidden />
                              {t('ontologyPage.turtle.goToLine', { line: errorLine })}
                            </Button>
                          ) : undefined
                        }
                      >
                        {errorLine !== null ? t('ontologyPage.turtle.parseErrorLine', { line: errorLine }) : t('ontologyPage.turtle.parseError')}
                      </InlineNotice>
                    ) : (
                      <InlineNotice tone="error" title={t('ontologyPage.turtle.failedTitle')}>
                        {message(generate.error)}
                      </InlineNotice>
                    )}
                  </div>
                ) : null}
                <TurtleEditor
                  ref={editor}
                  value={editing ? draft : text}
                  readOnly={!editing}
                  onChange={setDraft}
                  aria-label={t('ontologyPage.turtle.editorLabel')}
                  aria-describedby={generate.isError ? errorId : undefined}
                  aria-invalid={errorLine !== undefined}
                  className={EDITOR_SIZE}
                />
              </>
            )}
          </QueryState>
        </div>
      </Card>

      <Dialog
        open={result !== null}
        onOpenChange={(open) => {
          if (!open) setResult(null);
        }}
      >
        <DialogContent closeLabel={t('common.close')}>
          {result ? <ImportResultView result={result} mode="turtle" onClose={() => setResult(null)} /> : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) blocker.reset?.();
        }}
      >
        <DialogContent closeLabel={t('common.close')}>
          <DialogTitle>{t('ontologyPage.turtle.discardTitle')}</DialogTitle>
          <DialogDescription>{t('ontologyPage.turtle.discardDescription')}</DialogDescription>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('ontologyPage.turtle.keepEditing')}</DialogClose>
            <Button variant="destructive" onClick={() => blocker.proceed?.()}>
              {t('ontologyPage.turtle.discard')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
