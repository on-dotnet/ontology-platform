import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown, RefreshCw } from 'lucide-react';
import { useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { TurtleEditor, type TurtleEditorHandle } from '@/components/code/turtle-editor';
import { InfoTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { ontologyKeys, turtlePrefixes, useElementDetail, useOntologyTurtle, type EditItem, type Element } from '@/features/ontologies/api';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

import { isStale, useSaveEdits } from './edit-actions';

interface AxiomFormDialogProps {
  ontologyId: string;
  open: boolean;
  /** The axiom to change; a new one is written when unset. */
  elementId?: string;
  onClose: () => void;
}

/** Writes or rewrites one advanced axiom as a Turtle fragment (spec 002, section 7). */
export function AxiomFormDialog({ ontologyId, open, elementId, onClose }: AxiomFormDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto">
        {open ? (
          elementId ? (
            <EditAxiom ontologyId={ontologyId} elementId={elementId} onDone={onClose} />
          ) : (
            <AxiomForm ontologyId={ontologyId} onDone={onClose} />
          )
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function EditAxiom({ ontologyId, elementId, onDone }: { ontologyId: string; elementId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const detail = useElementDetail(ontologyId, elementId);
  // Bumped after reloading a changed axiom, so the form starts again from the fresh fragment.
  const [generation, setGeneration] = useState(0);
  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ontologyKeys.all });
    setGeneration((value) => value + 1);
  };
  return (
    <QueryState
      query={detail}
      loading={
        <div className="space-y-4" role="status" aria-busy>
          <DialogTitle className="sr-only">{t('common.loading')}</DialogTitle>
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-56 rounded-lg" />
        </div>
      }
    >
      {(element) => (
        <AxiomForm key={`${element.revision}-${generation}`} ontologyId={ontologyId} element={element} onDone={onDone} onReload={reload} />
      )}
    </QueryState>
  );
}

interface AxiomFormProps {
  ontologyId: string;
  /** The axiom being changed; undefined when writing a new one. */
  element?: Element;
  onDone: () => void;
  /** Loads the axiom again after someone else changed it. */
  onReload?: () => Promise<void>;
}

function AxiomForm({ ontologyId, element, onDone, onReload }: AxiomFormProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const labelId = useId();
  const hintId = useId();
  const errorId = useId();
  const editor = useRef<TurtleEditorHandle>(null);
  const { apply, mutation } = useSaveEdits(ontologyId);
  const initial = element?.turtle ?? '';
  const [turtle, setTurtle] = useState(initial);
  const [touched, setTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [unchanged, setUnchanged] = useState(false);
  const [reloading, setReloading] = useState(false);

  const missing = turtle.trim() === '';
  const showMissing = missing && (touched || submitted);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (missing) {
      editor.current?.focus();
      return;
    }
    if (element && turtle === initial) {
      setUnchanged(true);
      return;
    }
    const item: EditItem = element
      ? { op: 'update', kind: 'axiom', targetElementId: element.id, targetRevision: element.revision, fields: { turtle } }
      : { op: 'create', kind: 'axiom', tempRef: 'new:1', fields: { turtle } };
    mutation.mutate({ items: [item], appliedTitle: t('ontologyPage.edit.saved') }, { onSuccess: onDone });
  };

  const reload = async () => {
    if (!onReload) return;
    setReloading(true);
    try {
      await onReload();
    } finally {
      setReloading(false);
    }
  };

  return (
    <>
      <DialogTitle>{element ? t('ontologyPage.axiom.editTitle') : t('ontologyPage.axiom.createTitle')}</DialogTitle>
      <DialogDescription>{apply ? t('ontologyPage.form.appliesDescription') : t('ontologyPage.form.reviewDescription')}</DialogDescription>
      <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
        {unchanged ? <InlineNotice tone="info">{t('ontologyPage.form.nothingChanged')}</InlineNotice> : null}
        {mutation.isError ? (
          isStale(mutation.error) && onReload ? (
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
              {t('ontologyPage.form.staleDescription')}
            </InlineNotice>
          ) : (
            // axiom.invalid and axiom.maps_to_element say what is wrong and what to do instead.
            <InlineNotice tone="error" title={t('ontologyPage.form.failedTitle')}>
              {message(mutation.error)}
            </InlineNotice>
          )
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <span id={labelId} className="inline-flex items-center gap-1 text-sm font-medium text-foreground">
              {t('ontologyPage.axiom.fragment')}
              <span className="text-error-strong" aria-hidden>
                *
              </span>
            </span>
            <InfoTip label={t('ontologyPage.axiom.fragmentInfoLabel')}>{t('ontologyPage.axiom.fragmentInfo')}</InfoTip>
          </div>
          <OntologyPrefixes ontologyId={ontologyId} hintId={hintId} />
          <TurtleEditor
            ref={editor}
            value={turtle}
            onChange={(value) => {
              setUnchanged(false);
              setTurtle(value);
            }}
            onBlur={() => setTouched(true)}
            aria-labelledby={labelId}
            aria-describedby={showMissing ? `${hintId} ${errorId}` : hintId}
            aria-invalid={showMissing}
            aria-required
            className="h-56"
          />
          {showMissing ? (
            <p id={errorId} className="text-sm text-error-strong">
              {t('ontologyPage.axiom.fragmentRequired')}
            </p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
          <Button type="submit" loading={mutation.isPending}>
            {apply ? t('ontologyPage.edit.save') : t('ontologyPage.edit.submitForReview')}
          </Button>
        </div>
      </form>
    </>
  );
}

/** "You can use the ontology's prefixes", with the list (from the working version's export) folded away. */
function OntologyPrefixes({ ontologyId, hintId }: { ontologyId: string; hintId: string }) {
  const { t } = useTranslation();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const exported = useOntologyTurtle(ontologyId);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p id={hintId} className="text-xs text-muted-foreground">
          {t('ontologyPage.axiom.prefixesHint')}
        </p>
        <QueryState query={exported} loading={<Skeleton className="h-4 w-24" />}>
          {(text) => {
            const count = turtlePrefixes(text).length;
            return count > 0 ? (
              <button
                type="button"
                aria-expanded={open}
                aria-controls={open ? listId : undefined}
                onClick={() => setOpen((value) => !value)}
                className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary-strong hover:underline"
              >
                <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
                {open ? t('ontologyPage.axiom.hidePrefixes') : t('ontologyPage.axiom.showPrefixes', { count })}
              </button>
            ) : null;
          }}
        </QueryState>
      </div>
      {open && exported.data ? (
        <ul
          id={listId}
          aria-label={t('ontologyPage.axiom.prefixesLabel')}
          className="max-h-40 space-y-0.5 overflow-y-auto rounded-lg border border-border bg-muted px-3 py-2 font-mono text-xs"
        >
          {turtlePrefixes(exported.data).map((prefix) => (
            <li key={prefix.name} className="flex min-w-0 gap-2">
              <span className="shrink-0 font-semibold text-foreground">{prefix.name}:</span>
              <span className="min-w-0 break-all text-muted-foreground">{prefix.iri}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
