import { useMutation } from '@tanstack/react-query';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { DATATYPES } from '@/features/ontologies/api';
import { useErrorMessage } from '@/i18n/error-message';

import { patchItem, type ChangeItem } from './api';
import {
  editableFields,
  effectiveFields,
  entityTypeOptions,
  fromEditForm,
  itemLabel,
  refLabel,
  toEditForm,
  validateEdit,
  type EditField,
  type EditForm,
  type RefContext,
} from './item-fields';

interface ChangeItemEditDialogProps {
  changeSetId: string;
  /** The item being edited; the dialog is closed when null. */
  item: ChangeItem | null;
  items: readonly ChangeItem[];
  context: RefContext;
  onClose: () => void;
  onSaved: (item: ChangeItem) => void;
}

/** Edits an AI proposal with the same fields as the element; merges use the edited values. */
export function ChangeItemEditDialog({ changeSetId, item, items, context, onClose, onSaved }: ChangeItemEditDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={item !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] w-[min(42rem,calc(100vw-2rem))] overflow-y-auto">
        {item ? (
          <>
            <DialogTitle>{t('review.edit.title', { name: itemLabel(item, context) })}</DialogTitle>
            <DialogDescription>{t(`review.edit.description.${item.kind}`)}</DialogDescription>
            <EditItemForm key={item.id} changeSetId={changeSetId} item={item} items={items} context={context} onSaved={onSaved} />
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface EditItemFormProps {
  changeSetId: string;
  item: ChangeItem;
  items: readonly ChangeItem[];
  context: RefContext;
  onSaved: (item: ChangeItem) => void;
}

function EditItemForm({ changeSetId, item, items, context, onSaved }: EditItemFormProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const baseId = useId();
  const [form, setForm] = useState<EditForm>(() => toEditForm(effectiveFields(item), t('common.listSeparator')));
  const [touched, setTouched] = useState<ReadonlySet<EditField>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const fields = new Set(editableFields(item.kind, item.op));
  const errors = validateEdit(item.kind, item.op, form, item.tempRef);
  const errorCount = Object.keys(errors).length;

  const mutation = useMutation({
    mutationFn: () => patchItem(changeSetId, item.id, { edited: fromEditForm(item.kind, item.op, form) }),
    onSuccess: onSaved,
  });

  const set = <K extends EditField>(field: K, value: EditForm[K]) => setForm((current) => ({ ...current, [field]: value }));
  const touch = (field: EditField) => setTouched((current) => new Set(current).add(field));
  const fieldId = (field: EditField) => `${baseId}-${field}`;
  const errorFor = (field: EditField) => {
    const key = errors[field];
    return key && (submitted || touched.has(field)) ? t(key) : undefined;
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (errorCount > 0) {
      const first = Object.keys(errors)[0];
      if (first) document.getElementById(fieldId(first as EditField))?.focus();
      return;
    }
    mutation.mutate();
  };

  const options = entityTypeOptions(items, context, item.tempRef);
  const refSelect = (field: 'parentRef' | 'domainRef' | 'rangeRef', emptyLabel: string) => {
    const value = form[field];
    const known = value === '' || options.some((option) => option.value === value);
    return (
      <NativeSelect
        id={fieldId(field)}
        value={value}
        aria-invalid={errorFor(field) ? true : undefined}
        aria-describedby={errorFor(field) ? `${fieldId(field)}-error` : undefined}
        onChange={(event) => set(field, event.target.value)}
        onBlur={() => touch(field)}
      >
        <option value="">{emptyLabel}</option>
        {known ? null : <option value={value}>{refLabel(value, context) ?? t('review.unknownType')}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.isNew ? t('review.edit.newOption', { name: option.label }) : option.label}
          </option>
        ))}
      </NativeSelect>
    );
  };

  const textInput = (field: 'localName' | 'labelZh' | 'labelEn' | 'unit' | 'synonymsZh' | 'synonymsEn', extra: { placeholder?: string; mono?: boolean } = {}) => (
    <Input
      id={fieldId(field)}
      value={form[field]}
      placeholder={extra.placeholder}
      className={extra.mono ? 'font-mono' : undefined}
      aria-invalid={errorFor(field) ? true : undefined}
      aria-describedby={errorFor(field) ? `${fieldId(field)}-error` : undefined}
      onChange={(event) => set(field, event.target.value)}
      onBlur={() => touch(field)}
    />
  );

  const field = (name: EditField, label: string, control: ReactNode, required = false, className?: string) =>
    fields.has(name) ? (
      <div className={className ?? 'space-y-2'}>
        <Label htmlFor={fieldId(name)} required={required}>
          {label}
        </Label>
        {control}
        {errorFor(name) ? (
          <p id={`${fieldId(name)}-error`} className="text-sm text-error-strong">
            {errorFor(name)}
          </p>
        ) : null}
      </div>
    ) : null;

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-5 space-y-4">
      {submitted && errorCount > 0 ? (
        <InlineNotice tone="error">{t('review.edit.validationSummary', { count: errorCount })}</InlineNotice>
      ) : null}
      {mutation.isError ? (
        <InlineNotice tone="error" title={t('review.edit.failedTitle')}>
          {message(mutation.error)}
        </InlineNotice>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        {field('labelZh', t('review.fields.labelZh'), textInput('labelZh'), true)}
        {field('labelEn', t('review.fields.labelEn'), textInput('labelEn'))}
      </div>
      {field('localName', t('review.fields.localName'), textInput('localName', { mono: true }), true)}
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
      {field('parentRef', t('review.fields.parentRef'), refSelect('parentRef', t('review.edit.noParent')))}
      <div className="grid gap-4 sm:grid-cols-2">
        {field(
          'domainRef',
          t(item.kind === 'property' ? 'review.fields.propertyDomainRef' : 'review.fields.domainRef'),
          refSelect('domainRef', t('review.edit.chooseType')),
          true,
        )}
        {field('rangeRef', t('review.fields.rangeRef'), refSelect('rangeRef', t('review.edit.chooseType')), true)}
        {field(
          'datatype',
          t('review.fields.datatype'),
          <NativeSelect
            id={fieldId('datatype')}
            value={form.datatype}
            aria-invalid={errorFor('datatype') ? true : undefined}
            aria-describedby={errorFor('datatype') ? `${fieldId('datatype')}-error` : undefined}
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
          true,
        )}
        {field('unit', t('review.fields.unit'), textInput('unit', { placeholder: t('review.edit.unitPlaceholder') }))}
      </div>
      {fields.has('required') || fields.has('multiple') ? (
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

      <div className="flex justify-end gap-2 pt-2">
        <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
        <Button type="submit" loading={mutation.isPending}>
          {t('review.edit.save')}
        </Button>
      </div>
    </form>
  );
}
