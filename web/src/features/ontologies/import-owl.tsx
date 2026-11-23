import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ClipboardCheck, FileUp } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { WarnTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useErrorMessage } from '@/i18n/error-message';
import { formatBytes } from '@/lib/format';

import {
  IMPORT_ACCEPT,
  importIntoOntology,
  MAX_IMPORT_MB,
  ontologyKeys,
  type ImportResult,
  type OntologySummary,
} from './api';

const MB = 1024 * 1024;
const COUNT_KEYS = ['create', 'update', 'delete', 'restore'] as const;

/** Localized import failure; syntax errors name the line (and column) when the server knows it. */
export function useImportErrorMessage(): (error: unknown) => string {
  const { t } = useTranslation();
  const message = useErrorMessage();
  return (error: unknown) => {
    if (isApiError(error) && error.code === 'import.parse_error') {
      const { line, column } = error.body;
      if (typeof line === 'number') {
        return typeof column === 'number'
          ? t('ontologies.import.parseErrorAt', { line, column })
          : t('ontologies.import.parseErrorLine', { line });
      }
    }
    return message(error);
  };
}

/** Invalidates what an import changes: ontologies and their counts, change sets, the workbench. */
export function useRefreshAfterImport(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ontologyKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['change-sets'] }),
      queryClient.invalidateQueries({ queryKey: ['workbench'] }),
    ]);
  };
}

interface ImportFormProps {
  /** Offers the optional ontology name (new ontologies only). */
  withName?: boolean;
  run: (file: File, name: string | undefined) => Promise<ImportResult>;
  onImported: (result: ImportResult) => void | Promise<void>;
}

/** File (and optional name) of an OWL import, validated on the client for presence and size. */
export function ImportForm({ withName = false, run, onImported }: ImportFormProps) {
  const { t, i18n } = useTranslation();
  const importError = useImportErrorMessage();
  const inputRef = useRef<HTMLInputElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const labelId = useId();
  const errorId = useId();
  const hintId = useId();
  const nameId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const mutation = useMutation({
    mutationFn: ({ chosen, chosenName }: { chosen: File; chosenName: string | undefined }) => run(chosen, chosenName),
    onSuccess: (result) => onImported(result),
  });

  let fileError: string | undefined;
  if (!file) fileError = t('ontologies.import.fileRequired');
  else if (file.size > MAX_IMPORT_MB * MB) fileError = t('ontologies.import.fileTooLarge', { size: MAX_IMPORT_MB });
  // A wrong size is shown as soon as the file is chosen; a missing file only after submitting.
  const showFileError = Boolean(fileError) && (submitted || file !== null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (fileError || !file) {
      buttonRef.current?.focus();
      return;
    }
    mutation.mutate({ chosen: file, chosenName: withName && name.trim() ? name.trim() : undefined });
  };

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
      {mutation.isError ? (
        <InlineNotice tone="error" title={t('ontologies.import.failedTitle')}>
          {importError(mutation.error)}
        </InlineNotice>
      ) : null}

      <div className="space-y-2" role="group" aria-labelledby={labelId}>
        <span id={labelId} className="inline-flex items-center gap-1 text-sm font-medium text-foreground">
          {t('ontologies.import.file')}
          <span className="text-error-strong" aria-hidden>
            *
          </span>
        </span>
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border bg-background px-3 py-3">
          <input
            ref={inputRef}
            type="file"
            accept={IMPORT_ACCEPT}
            tabIndex={-1}
            className="sr-only"
            aria-label={t('ontologies.import.fileInputLabel')}
            onChange={(event) => {
              const chosen = event.target.files?.[0] ?? null;
              // Allow choosing the same file again after fixing it.
              event.target.value = '';
              if (chosen) {
                setFile(chosen);
                mutation.reset();
              }
            }}
          />
          <Button
            ref={buttonRef}
            variant="secondary"
            size="sm"
            aria-describedby={showFileError ? errorId : hintId}
            onClick={() => inputRef.current?.click()}
          >
            <FileUp aria-hidden />
            {file ? t('ontologies.import.changeFile') : t('ontologies.import.chooseFile')}
          </Button>
          {file ? (
            <span className="min-w-0 flex-1 truncate text-sm text-foreground" title={file.name}>
              <span className="font-medium">{file.name}</span>
              <span className="ml-2 text-xs tabular-nums text-muted-foreground">
                {formatBytes(file.size, i18n.resolvedLanguage ?? i18n.language)}
              </span>
            </span>
          ) : null}
        </div>
        <p id={hintId} className="text-xs text-muted-foreground">
          {t('ontologies.import.fileHint', { size: MAX_IMPORT_MB })}
        </p>
        {showFileError ? (
          <p id={errorId} className="text-sm text-error-strong">
            {fileError}
          </p>
        ) : null}
      </div>

      {withName ? (
        <div className="space-y-2">
          <Label htmlFor={nameId}>{t('ontologies.create.name')}</Label>
          <Input
            id={nameId}
            value={name}
            maxLength={100}
            placeholder={t('ontologies.import.namePlaceholder')}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
      ) : null}

      <div className="flex justify-end gap-2 pt-2">
        <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
        <Button type="submit" loading={mutation.isPending}>
          {t('ontologies.import.submit')}
        </Button>
      </div>
    </form>
  );
}

interface ImportResultViewProps {
  result: ImportResult;
  /** The import created the ontology (rather than comparing with an existing one). */
  created: boolean;
  onClose: () => void;
}

/** What the import found: counts per operation, warnings, and the way to the change set. */
export function ImportResultView({ result, created, onClose }: ImportResultViewProps) {
  const { t } = useTranslation();
  const headingRef = useRef<HTMLDivElement>(null);
  const { changeSetId, counts, warnings } = result;

  // The form is gone: move focus to the result so keyboard and screen reader users follow.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  let title: string;
  let description: string;
  if (created) {
    title = t('ontologies.import.createdTitle', { name: result.ontology.name });
    description = changeSetId ? t('ontologies.import.reviewDescription') : t('ontologies.import.nothingToReview');
  } else {
    title = changeSetId ? t('ontologies.import.importedTitle') : t('ontologies.import.noDifferenceTitle');
    description = changeSetId ? t('ontologies.import.reviewDescription') : t('ontologies.import.noDifference');
  }

  return (
    <div className="space-y-4">
      <div ref={headingRef} tabIndex={-1} className="outline-none">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </div>

      {changeSetId ? (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label={t('ontologies.import.countsLabel')}>
          {COUNT_KEYS.map((key) => (
            <div key={key} className="rounded-lg bg-muted px-3 py-2">
              <dt className="text-xs text-muted-foreground">{t(`ontologies.import.counts.${key}`)}</dt>
              <dd className="text-lg font-semibold tabular-nums text-foreground">{counts[key]}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {warnings.length > 0 ? (
        <ul className="space-y-1.5" aria-label={t('ontologies.import.warningsLabel')}>
          {warnings.map((warning) => {
            const label = t(`ontologies.import.warnings.${warning.code}.label`, { count: warning.count });
            return (
              <li key={warning.code} className="flex items-center gap-1.5 text-sm text-foreground">
                <WarnTip label={label}>{t(`ontologies.import.warnings.${warning.code}.description`)}</WarnTip>
                <span>{label}</span>
              </li>
            );
          })}
        </ul>
      ) : null}

      <div className="flex justify-end gap-2 pt-2">
        <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.close')}</DialogClose>
        {changeSetId ? (
          <Link to="/review/$changeSetId" params={{ changeSetId }} className={buttonVariants({ variant: 'primary' })} onClick={onClose}>
            <ClipboardCheck aria-hidden />
            {t('ontologies.import.goReview')}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

interface ImportOwlDialogProps {
  ontology: OntologySummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Imports a file into the current ontology: the differences from the working version become a change set. */
export function ImportOwlDialog({ ontology, open, onOpenChange }: ImportOwlDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')}>
        <ImportIntoBody ontology={ontology} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function ImportIntoBody({ ontology, onClose }: { ontology: OntologySummary; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefreshAfterImport();
  const [result, setResult] = useState<ImportResult | null>(null);
  if (result) return <ImportResultView result={result} created={false} onClose={onClose} />;
  return (
    <>
      <DialogTitle>{t('ontologies.import.intoTitle', { name: ontology.name })}</DialogTitle>
      <DialogDescription>{t('ontologies.import.intoDescription')}</DialogDescription>
      <ImportForm
        run={(file) => importIntoOntology(ontology.id, file)}
        onImported={async (imported) => {
          await refresh();
          setResult(imported);
        }}
      />
    </>
  );
}
