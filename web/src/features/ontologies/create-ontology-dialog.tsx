import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Textarea } from '@/components/ui/textarea';
import { useErrorMessage } from '@/i18n/error-message';

import { createOntology, importOntology, ontologyKeys, type ImportResult, type OntologySummary } from './api';
import { ImportForm, ImportResultView, useRefreshAfterImport } from './import-owl';

export type CreateMethod = 'blank' | 'import';

interface CreateOntologyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (ontology: OntologySummary) => void;
  /**
   * Offers "import from an OWL file" next to the blank ontology. Off while documents wait to be
   * uploaded: that dialog only names the ontology they go into.
   */
  allowImport?: boolean;
  initialMethod?: CreateMethod;
  /** Called once the import created the ontology; the dialog stays open on the result. */
  onImported?: (result: ImportResult) => void;
}

/** Names a new ontology, or creates one from an OWL file when `allowImport` is set. */
export function CreateOntologyDialog({
  open,
  onOpenChange,
  onCreated,
  allowImport = false,
  initialMethod = 'blank',
  onImported,
}: CreateOntologyDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')}>
        {allowImport ? (
          <CreateOrImport
            initialMethod={initialMethod}
            onCreated={onCreated}
            onImported={onImported}
            onClose={() => onOpenChange(false)}
          />
        ) : (
          <>
            <DialogTitle>{t('ontologies.create.title')}</DialogTitle>
            <DialogDescription>{t('ontologies.create.description')}</DialogDescription>
            <CreateOntologyForm onCreated={onCreated} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

interface CreateOrImportProps {
  initialMethod: CreateMethod;
  onCreated: (ontology: OntologySummary) => void;
  onImported: ((result: ImportResult) => void) | undefined;
  onClose: () => void;
}

function CreateOrImport({ initialMethod, onCreated, onImported, onClose }: CreateOrImportProps) {
  const { t } = useTranslation();
  const refresh = useRefreshAfterImport();
  const [method, setMethod] = useState<CreateMethod>(initialMethod);
  const [result, setResult] = useState<ImportResult | null>(null);

  if (result) return <ImportResultView result={result} mode="created" onClose={onClose} />;
  return (
    <>
      <DialogTitle>{t('ontologies.create.standaloneTitle')}</DialogTitle>
      <DialogDescription>{t('ontologies.create.standaloneDescription')}</DialogDescription>
      <SegmentedControl
        legend={t('ontologies.create.method')}
        hideLegend
        className="mt-5"
        value={method}
        onValueChange={setMethod}
        options={[
          { value: 'blank', label: t('ontologies.create.methodBlank') },
          { value: 'import', label: t('ontologies.create.methodImport') },
        ]}
      />
      {method === 'import' ? (
        <ImportForm
          withName
          run={(file, name) => importOntology(file, name)}
          onImported={async (imported) => {
            await refresh();
            setResult(imported);
            onImported?.(imported);
          }}
        />
      ) : (
        <CreateOntologyForm onCreated={onCreated} />
      )}
    </>
  );
}

function CreateOntologyForm({ onCreated }: { onCreated: (ontology: OntologySummary) => void }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const queryClient = useQueryClient();
  const nameId = useId();
  const descriptionId = useId();
  const nameErrorId = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [touched, setTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const mutation = useMutation({
    mutationFn: createOntology,
    onSuccess: async (ontology) => {
      await queryClient.invalidateQueries({ queryKey: ontologyKeys.all });
      onCreated(ontology);
    },
  });

  const nameError = name.trim() ? undefined : t('ontologies.create.nameRequired');
  const showNameError = (touched || submitted) && nameError;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (nameError) {
      nameRef.current?.focus();
      return;
    }
    mutation.mutate({ name: name.trim(), ...(description.trim() ? { description: description.trim() } : {}) });
  };

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
      {submitted && nameError ? <InlineNotice tone="error">{t('ontologies.create.validationSummary')}</InlineNotice> : null}
      {mutation.isError ? (
        <InlineNotice tone="error" title={t('ontologies.create.failedTitle')}>
          {message(mutation.error)}
        </InlineNotice>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor={nameId} required>
          {t('ontologies.create.name')}
        </Label>
        <Input
          ref={nameRef}
          id={nameId}
          value={name}
          maxLength={100}
          placeholder={t('ontologies.create.namePlaceholder')}
          aria-required
          aria-invalid={showNameError ? true : undefined}
          aria-describedby={showNameError ? nameErrorId : undefined}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => setTouched(name.length > 0 || touched)}
        />
        {showNameError ? (
          <p id={nameErrorId} className="text-sm text-error-strong">
            {nameError}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor={descriptionId}>{t('ontologies.create.descriptionLabel')}</Label>
        <Textarea
          id={descriptionId}
          value={description}
          maxLength={500}
          rows={2}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
        <Button type="submit" loading={mutation.isPending}>
          {t('ontologies.create.submit')}
        </Button>
      </div>
    </form>
  );
}
