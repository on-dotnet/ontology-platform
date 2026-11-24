import { useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { DATATYPES, elementName, ontologyKeys, useElementDetail, useElements, type Element, type EditItem } from '@/features/ontologies/api';
import { useErrorMessage } from '@/i18n/error-message';

import { isStale, useSaveEdits } from './edit-actions';
import {
  formFields,
  formToFields,
  isFormKind,
  isRequired,
  suggestLocalName,
  toElementForm,
  usesPascalCase,
  validateElementForm,
  type ElementForm,
  type FormField,
  type FormKind,
  type FormMode,
  type RuleForm,
} from './element-form';
import { RuleEditor } from './rule-editor';

/** A new element of a kind, or an existing element to change. */
export type FormTarget = { kind: FormKind; elementId?: undefined } | { kind?: undefined; elementId: string };

interface ElementFormDialogProps {
  ontologyId: string;
  /** What the dialog makes or changes; closed when null. */
  target: FormTarget | null;
  onClose: () => void;
}

/** Creates or changes an object type, relation, property or constraint by hand (spec 002, section 6). */
export function ElementFormDialog({ ontologyId, target, onClose }: ElementFormDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto">
        {target?.elementId ? (
          <EditBody ontologyId={ontologyId} elementId={target.elementId} onDone={onClose} />
        ) : target?.kind ? (
          <CreateBody ontologyId={ontologyId} kind={target.kind} onDone={onClose} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function FormSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="space-y-4" role="status" aria-busy>
      <DialogTitle className="sr-only">{t('common.loading')}</DialogTitle>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-10 rounded-lg" />
      <Skeleton className="h-10 rounded-lg" />
      <Skeleton className="h-24 rounded-lg" />
    </div>
  );
}

function Loaded<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  return (
    <QueryState query={query} loading={<FormSkeleton />}>
      {children}
    </QueryState>
  );
}

function CreateBody({ ontologyId, kind, onDone }: { ontologyId: string; kind: FormKind; onDone: () => void }) {
  const elements = useElements(ontologyId);
  return <Loaded query={elements}>{(all) => <ElementFormBody ontologyId={ontologyId} kind={kind} elements={all} onDone={onDone} />}</Loaded>;
}

function EditBody({ ontologyId, elementId, onDone }: { ontologyId: string; elementId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const detail = useElementDetail(ontologyId, elementId);
  // Bumped after reloading a changed element, so the form starts again from the fresh values.
  const [generation, setGeneration] = useState(0);
  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ontologyKeys.all });
    setGeneration((value) => value + 1);
  };
  return (
    <Loaded query={detail}>
      {(element) => (
        <EditLoaded key={`${element.revision}-${generation}`} ontologyId={ontologyId} element={element} onDone={onDone} onReload={reload} />
      )}
    </Loaded>
  );
}

function EditLoaded({ ontologyId, element, onDone, onReload }: { ontologyId: string; element: Element; onDone: () => void; onReload: () => Promise<void> }) {
  const elements = useElements(ontologyId);
  const { kind } = element;
  if (!isFormKind(kind)) return null;
  return (
    <Loaded query={elements}>
      {(all) => <ElementFormBody ontologyId={ontologyId} kind={kind} element={element} elements={all} onDone={onDone} onReload={onReload} />}
    </Loaded>
  );
}

interface ElementFormBodyProps {
  ontologyId: string;
  kind: FormKind;
  /** The element being changed; undefined when creating. */
  element?: Element;
  /** Active elements, for the references a field may point to. */
  elements: readonly Element[];
  onDone: () => void;
  /** Loads the element again after someone else changed it. */
  onReload?: () => Promise<void>;
}

function ElementFormBody({ ontologyId, kind, element, elements, onDone, onReload }: ElementFormBodyProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const message = useErrorMessage();
  const baseId = useId();
  const separator = t('common.listSeparator');
  const { apply, mutation } = useSaveEdits(ontologyId);
  const [initial] = useState<ElementForm>(() => toElementForm(element, kind, separator));
  const [form, setForm] = useState<ElementForm>(initial);
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const [unchanged, setUnchanged] = useState(false);
  const [reloading, setReloading] = useState(false);
  // The local name follows the English name until the user types one of their own.
  const [ownLocalName, setOwnLocalName] = useState(false);

  const mode: FormMode = { kind, creating: !element, imported: element?.explicitIri ?? false };
  const fields = formFields(kind);
  const byId = new Map(elements.map((item) => [item.id, item]));
  const pathDatatype = (ref: string) => {
    const path = byId.get(ref);
    return path?.kind === 'property' ? path.datatype : null;
  };
  const errors = validateElementForm(mode, form, pathDatatype);
  const errorKeys = Object.keys(errors);

  const fieldId = (key: string) => `${baseId}-${key.replace(/[^A-Za-z0-9_-]/g, '-')}`;
  const touch = (key: string) => setTouched((current) => new Set(current).add(key));
  const errorFor = (key: string) => {
    const error = errors[key];
    return error && (submitted || touched.has(key)) ? t(error) : undefined;
  };
  const set = <K extends keyof ElementForm>(field: K, value: ElementForm[K]) => {
    setUnchanged(false);
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (errorKeys.length > 0) {
      document.getElementById(fieldId(errorKeys[0] ?? ''))?.focus();
      return;
    }
    const changes = formToFields(mode, form, initial, pathDatatype);
    if (element && Object.keys(changes).length === 0) {
      setUnchanged(true);
      return;
    }
    const item: EditItem = element
      ? { op: 'update', kind, targetElementId: element.id, targetRevision: element.revision, fields: changes }
      : { op: 'create', kind, tempRef: 'new:1', fields: changes };
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

  const title = element ? t('ontologyPage.form.editTitle', { name: elementName(element, language) || '—' }) : t(`ontologyPage.form.createTitle.${kind}`);

  // ---------- controls ----------

  const describedBy = (key: string) => (errorFor(key) ? `${fieldId(key)}-error` : undefined);
  const nameOf = (item: Element) => elementName(item, language) || '—';

  const textInput = (name: 'labelZh' | 'labelEn' | 'synonymsZh' | 'synonymsEn' | 'unit', extra: { placeholder?: string } = {}) => (
    <Input
      id={fieldId(name)}
      value={form[name]}
      placeholder={extra.placeholder}
      aria-invalid={errorFor(name) ? true : undefined}
      aria-describedby={describedBy(name)}
      onChange={(event) => {
        const value = event.target.value;
        set(name, value);
        if (name === 'labelEn' && mode.creating && !ownLocalName) set('localName', suggestLocalName(value, kind));
      }}
      onBlur={() => touch(name)}
    />
  );

  const refSelect = (name: 'parentRef' | 'domainRef' | 'rangeRef' | 'inverseRef', options: readonly Element[], emptyLabel: string) => {
    const value = form[name];
    const known = value === '' || options.some((option) => option.id === value);
    return (
      <NativeSelect
        id={fieldId(name)}
        value={value}
        aria-invalid={errorFor(name) ? true : undefined}
        aria-describedby={describedBy(name)}
        onChange={(event) => set(name, event.target.value)}
        onBlur={() => touch(name)}
      >
        <option value="">{emptyLabel}</option>
        {known ? null : <option value={value}>{t('ontologyPage.detail.unknownElement')}</option>}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {nameOf(option)}
          </option>
        ))}
      </NativeSelect>
    );
  };

  const field = (name: FormField, label: string, control: ReactNode, extra: { hint?: ReactNode } = {}) =>
    fields.has(name) ? (
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label htmlFor={fieldId(name)} required={isRequired(name, mode)}>
            {label}
          </Label>
          {extra.hint}
        </div>
        {control}
        {errorFor(name) ? (
          <p id={`${fieldId(name)}-error`} className="text-sm text-error-strong">
            {errorFor(name)}
          </p>
        ) : null}
      </div>
    ) : null;

  const types = elements.filter((item) => item.kind === 'entity_type');
  const parentOptions = types.filter((item) => !element || !isDescendantOrSelf(item.id, element.id, byId));
  const inverseOptions = elements.filter((item) => item.kind === 'relation_type' && item.id !== element?.id);

  const localNameControl = mode.creating ? (
    <Input
      id={fieldId('localName')}
      value={form.localName}
      className="font-mono"
      aria-invalid={errorFor('localName') ? true : undefined}
      aria-describedby={describedBy('localName')}
      onChange={(event) => {
        setOwnLocalName(event.target.value !== '');
        set('localName', event.target.value);
      }}
      onBlur={() => touch('localName')}
    />
  ) : (
    <Input id={fieldId('localName')} value={form.localName} readOnly className="bg-muted font-mono text-muted-foreground" />
  );
  const localNameHint = (
    <InfoTip label={t('ontologyPage.form.localNameInfoLabel')}>
      {mode.creating
        ? t(usesPascalCase(kind) ? 'ontologyPage.form.localNameHintPascal' : 'ontologyPage.form.localNameHintCamel')
        : t('ontologyPage.form.localNameFixed')}
    </InfoTip>
  );

  return (
    <>
      <DialogTitle>{title}</DialogTitle>
      <DialogDescription>{apply ? t('ontologyPage.form.appliesDescription') : t('ontologyPage.form.reviewDescription')}</DialogDescription>
      <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
        {submitted && errorKeys.length > 0 ? (
          <InlineNotice tone="error">{t('review.edit.validationSummary', { count: errorKeys.length })}</InlineNotice>
        ) : null}
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
            <InlineNotice tone="error" title={t('ontologyPage.form.failedTitle')}>
              {message(mutation.error)}
            </InlineNotice>
          )
        ) : null}

        {mode.imported && element?.iri ? (
          <dl className="space-y-1 rounded-lg bg-muted px-3 py-2 text-xs">
            <dt className="font-semibold text-muted-foreground">{t('ontologyPage.detail.iri')}</dt>
            <dd className="break-all font-mono text-foreground">{element.iri}</dd>
          </dl>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          {field('labelZh', t('review.fields.labelZh'), textInput('labelZh'))}
          {field('labelEn', t('review.fields.labelEn'), textInput('labelEn'))}
        </div>
        {field('localName', t('review.fields.localName'), localNameControl, { hint: localNameHint })}
        {field(
          'definitionZh',
          t('review.fields.definitionZh'),
          <Textarea id={fieldId('definitionZh')} value={form.definitionZh} rows={3} onChange={(event) => set('definitionZh', event.target.value)} />,
        )}
        {field(
          'definitionEn',
          t('review.fields.definitionEn'),
          <Textarea id={fieldId('definitionEn')} value={form.definitionEn} rows={2} onChange={(event) => set('definitionEn', event.target.value)} />,
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {field('synonymsZh', t('review.fields.synonymsZh'), textInput('synonymsZh', { placeholder: t('review.edit.synonymsPlaceholder') }))}
          {field('synonymsEn', t('review.fields.synonymsEn'), textInput('synonymsEn', { placeholder: t('review.edit.synonymsPlaceholder') }))}
        </div>

        {field('parentRef', t('review.fields.parentRef'), refSelect('parentRef', parentOptions, t('review.edit.noParent')))}
        <div className="grid gap-4 sm:grid-cols-2">
          {field(
            'domainRef',
            t(kind === 'property' ? 'review.fields.propertyDomainRef' : kind === 'constraint' ? 'review.fields.targetRef' : 'review.fields.domainRef'),
            refSelect('domainRef', types, t('review.edit.chooseType')),
          )}
          {field('rangeRef', t('review.fields.rangeRef'), refSelect('rangeRef', types, t('review.edit.chooseType')))}
          {field('inverseRef', t('review.fields.inverseRef'), refSelect('inverseRef', inverseOptions, t('ontologyPage.form.noInverse')))}
          {field(
            'datatype',
            t('review.fields.datatype'),
            <NativeSelect
              id={fieldId('datatype')}
              value={form.datatype}
              aria-invalid={errorFor('datatype') ? true : undefined}
              aria-describedby={describedBy('datatype')}
              onChange={(event) => set('datatype', event.target.value)}
              onBlur={() => touch('datatype')}
            >
              <option value="">{t('review.edit.chooseDatatype')}</option>
              {DATATYPES.map((datatype) => (
                <option key={datatype} value={datatype}>
                  {t(`datatypes.${datatype}`)}
                </option>
              ))}
            </NativeSelect>,
          )}
          {field('unit', t('review.fields.unit'), textInput('unit', { placeholder: t('review.edit.unitPlaceholder') }))}
        </div>
        {fields.has('required') ? (
          <fieldset className="m-0 flex flex-wrap gap-6 border-0 p-0">
            <legend className="sr-only">{t('review.edit.cardinality')}</legend>
            {(['required', 'multiple'] as const).map((name) => (
              <label key={name} className="inline-flex cursor-pointer items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  className="size-4 cursor-pointer accent-primary"
                  checked={form[name]}
                  onChange={(event) => set(name, event.target.checked)}
                />
                {t(`review.fields.${name}`)}
              </label>
            ))}
          </fieldset>
        ) : null}

        {kind === 'constraint' ? (
          <RuleEditor
            rules={form.rules}
            elements={elements}
            language={language}
            onChange={(rules: RuleForm[]) => set('rules', rules)}
            fieldId={fieldId}
            errorFor={errorFor}
            onTouch={touch}
          />
        ) : null}

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

/** Whether `id` is `ancestorId` or one of its subtypes: a type cannot become its own parent. */
function isDescendantOrSelf(id: string, ancestorId: string, byId: ReadonlyMap<string, Element>): boolean {
  const seen = new Set<string>();
  let current: string | null | undefined = id;
  while (current && !seen.has(current)) {
    if (current === ancestorId) return true;
    seen.add(current);
    current = byId.get(current)?.parentId;
  }
  return false;
}
