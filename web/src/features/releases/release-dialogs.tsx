import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { useToast } from '@/components/feedback/toast';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { elementLabel, ontologyKeys, useElements, type OntologySummary } from '@/features/ontologies/api';
import { lookupText, useErrorMessage } from '@/i18n/error-message';

import { activateRelease, publishRelease, releaseKeys, releaseProblems, type ReleaseProblem, type ReleaseSummary } from './api';

interface PublishReleaseDialogProps {
  ontology: OntologySummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Title and notes for a new immutable release; lists validation problems when the server refuses. */
export function PublishReleaseDialog({ ontology, open, onOpenChange }: PublishReleaseDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogTitle>{t('releases.publish.title')}</DialogTitle>
        <DialogDescription>{t('releases.publish.description')}</DialogDescription>
        <PublishForm ontology={ontology} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function PublishForm({ ontology, onDone }: { ontology: OntologySummary; onDone: () => void }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const titleId = useId();
  const notesId = useId();
  const titleErrorId = useId();
  const titleRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [touched, setTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const mutation = useMutation({
    mutationFn: () => publishRelease(ontology.id, { title: title.trim(), ...(notes.trim() ? { notes: notes.trim() } : {}) }),
    onSuccess: async (release) => {
      toast.success(t('releases.publish.published', { version: release.version }));
      onDone();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: releaseKeys.list(ontology.id) }),
        queryClient.invalidateQueries({ queryKey: ontologyKeys.all }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ]);
    },
  });

  const titleError = title.trim() ? undefined : t('releases.publish.titleRequired');
  const showTitleError = (touched || submitted) && titleError;
  const problems = mutation.isError ? releaseProblems(mutation.error) : null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (titleError) {
      titleRef.current?.focus();
      return;
    }
    mutation.mutate();
  };

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
      {ontology.openChangeSetCount > 0 ? (
        <InlineNotice tone="warning" title={t('releases.publish.openChangeSetsTitle', { count: ontology.openChangeSetCount })}>
          {t('releases.publish.openChangeSetsDescription')}
        </InlineNotice>
      ) : null}
      {submitted && titleError ? <InlineNotice tone="error">{t('releases.publish.validationSummary')}</InlineNotice> : null}
      {problems ? (
        <ProblemList ontologyId={ontology.id} problems={problems} />
      ) : mutation.isError ? (
        <InlineNotice tone="error" title={t('releases.publish.failedTitle')}>
          {message(mutation.error)}
        </InlineNotice>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor={titleId} required>
          {t('releases.publish.titleLabel')}
        </Label>
        <Input
          ref={titleRef}
          id={titleId}
          value={title}
          maxLength={200}
          placeholder={t('releases.publish.titlePlaceholder')}
          aria-required
          aria-invalid={showTitleError ? true : undefined}
          aria-describedby={showTitleError ? titleErrorId : undefined}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => setTouched(title.length > 0 || touched)}
        />
        {showTitleError ? (
          <p id={titleErrorId} className="text-sm text-error-strong">
            {titleError}
          </p>
        ) : null}
      </div>
      <div className="space-y-2">
        <Label htmlFor={notesId}>{t('releases.publish.notesLabel')}</Label>
        <Textarea id={notesId} value={notes} rows={3} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
        <Button type="submit" loading={mutation.isPending}>
          {t('releases.publish.submit')}
        </Button>
      </div>
    </form>
  );
}

/** Red banner with one line per validation problem, named by element and explained by code. */
function ProblemList({ ontologyId, problems }: { ontologyId: string; problems: readonly ReleaseProblem[] }) {
  const { t, i18n } = useTranslation();
  const elements = useElements(ontologyId);
  const language = i18n.resolvedLanguage ?? i18n.language;
  const byId = new Map((elements.data ?? []).map((element) => [element.id, element]));
  const describe = (problem: ReleaseProblem) =>
    lookupText(i18n, `releases.problems.${problem.code}`) ?? t('releases.problems.unknown');

  return (
    <InlineNotice tone="error" title={t('releases.publish.invalidTitle', { count: problems.length })}>
      <p>{t('releases.publish.invalidDescription')}</p>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
        {problems.map((problem, index) => {
          const element = problem.elementId ? byId.get(problem.elementId) : undefined;
          return (
            <li key={`${problem.code}-${problem.elementId ?? 'none'}-${index}`}>
              {element ? (
                <>
                  <span className="font-medium">{elementLabel(element, language)}</span>
                  {t('common.colon')}
                </>
              ) : null}
              {describe(problem)}
            </li>
          );
        })}
      </ul>
    </InlineNotice>
  );
}

interface ActivateReleaseDialogProps {
  ontology: OntologySummary;
  /** The release to make current; the dialog is closed when null. */
  release: ReleaseSummary | null;
  current: ReleaseSummary | undefined;
  onClose: () => void;
}

/** Confirms switching the current release, spelling out what changes. */
export function ActivateReleaseDialog({ ontology, release, current, onClose }: ActivateReleaseDialogProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (target: ReleaseSummary) => activateRelease(target.id),
    onSuccess: async (_, target) => {
      toast.success(t('releases.activate.done', { version: target.version }));
      onClose();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: releaseKeys.list(ontology.id) }),
        queryClient.invalidateQueries({ queryKey: ontologyKeys.all }),
      ]);
    },
  });

  return (
    <Dialog
      open={release !== null}
      onOpenChange={(open) => {
        if (!open) {
          mutation.reset();
          onClose();
        }
      }}
    >
      <DialogContent closeLabel={t('common.close')}>
        {release ? (
          <>
            <DialogTitle>{t('releases.activate.title', { version: release.version })}</DialogTitle>
            <DialogDescription className="mt-2 space-y-2">
              <span className="block">
                {current
                  ? t('releases.activate.change', { from: current.version, to: release.version })
                  : t('releases.activate.first', { to: release.version })}
              </span>
              <span className="block">{t('releases.activate.consequence', { to: release.version })}</span>
            </DialogDescription>
            {mutation.isError ? (
              <InlineNotice tone="error" title={t('releases.activate.failedTitle')} className="mt-4">
                {message(mutation.error)}
              </InlineNotice>
            ) : null}
            <div className="mt-6 flex justify-end gap-2">
              <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
              <Button loading={mutation.isPending} onClick={() => mutation.mutate(release)}>
                {t('releases.activate.confirm')}
              </Button>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
