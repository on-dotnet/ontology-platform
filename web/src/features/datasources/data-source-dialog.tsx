import { Minus, Plus } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { InfoTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { useErrorMessage } from '@/i18n/error-message';

import type { DataSource } from './api';
import { ConnectionTestResult } from './connection-test-result';
import {
  createRequest, initialForm, patchRequest, sslModes, testRequest, validationErrors,
  type Operation, type SourceForm, type TextField,
} from './data-source-form';

interface DataSourceDialogProps {
  source?: DataSource;
  onClose: () => void;
  onSaved: (source: DataSource) => void | Promise<void>;
}

const maxLengths = { name: 100, host: 255, database: 128, username: 128, password: 1024 };

export function DataSourceDialog({ source, onClose, onSaved }: DataSourceDialogProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const id = useId();
  // The revision and comparison values belong to the draft opened by the user.
  const [initial] = useState(source);
  const [form, setForm] = useState(() => initialForm(initial));
  const [touched, setTouched] = useState<Partial<Record<TextField, boolean>>>({});
  const [attempted, setAttempted] = useState<Operation | null>(null);
  const [pending, setPending] = useState<Operation | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<components['schemas']['ConnectionTest'] | null>(null);
  const nextRowId = useRef(form.schemas.length);
  const formRef = useRef<HTMLFormElement>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function change<K extends keyof SourceForm>(field: K, value: SourceForm[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setError(null);
    if (field !== 'name' && field !== 'allowSamples') setResult(null);
  }

  async function run(operation: Operation) {
    if (controller.current) return;
    setAttempted(operation);
    setError(null);
    setResult(null);
    const errors = validationErrors(form, Boolean(initial), operation);
    const [invalidField] = Object.keys(errors);
    if (invalidField) {
      const input = formRef.current?.elements.namedItem(invalidField);
      if (input instanceof HTMLElement) input.focus();
      return;
    }

    const request = new AbortController();
    const { signal } = request;
    controller.current = request;
    setPending(operation);
    try {
      if (operation === 'test') {
        const tested = await unwrap(api.POST('/api/data-sources/test', { body: testRequest(form, initial), signal }));
        if (!signal.aborted) setResult(tested);
      } else {
        const saved = initial
          ? await unwrap(api.PATCH('/api/data-sources/{id}', {
              params: { path: { id: initial.id } }, body: patchRequest(form, initial), signal,
            }))
          : await unwrap(api.POST('/api/data-sources', { body: createRequest(form), signal }));
        if (!signal.aborted) await onSaved(saved);
      }
    } catch (cause) {
      if (!signal.aborted) setError(cause);
    } finally {
      controller.current = null;
      if (!signal.aborted) setPending(null);
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run('save');
  }

  const errors = validationErrors(form, Boolean(initial), 'save');
  const showSummary = attempted && Object.keys(validationErrors(form, Boolean(initial), attempted)).length > 0;

  function input(field: TextField) {
    const label = t(`datasources.fields.${field}`);
    const required = field !== 'password' || !initial;
    const attemptedField = attempted === 'save' || (attempted === 'test' && field !== 'name');
    const problem = (touched[field] || attemptedField) && errors[field];
    const inputId = `${id}-${field}`;
    return (
      <div className="min-w-0 space-y-1">
        <Label htmlFor={inputId} required={required}>{label}</Label>
        <Input
          id={inputId}
          name={field}
          type={field === 'port' ? 'number' : field === 'password' ? 'password' : 'text'}
          value={form[field]}
          onChange={(event) => change(field, event.target.value)}
          onBlur={() => setTouched((current) => ({ ...current, [field]: true }))}
          required={required}
          aria-invalid={problem ? true : undefined}
          aria-describedby={problem ? `${inputId}-error` : undefined}
          {...(field === 'port' ? { min: 1, max: 65535, step: 1 } : { maxLength: maxLengths[field] })}
          autoComplete={field === 'password' ? 'new-password' : 'off'}
          placeholder={field === 'password' && initial?.hasCredential ? t('datasources.form.savedPassword') : undefined}
        />
        {problem && (
          <p className="text-sm text-error-strong" id={`${inputId}-error`}>
            {t(`datasources.form.${problem}`, { field: label })}
          </p>
        )}
      </div>
    );
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && pending !== 'save') onClose(); }}>
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] w-[min(38rem,calc(100vw-2rem))] overflow-y-auto"
        closeLabel={pending === 'save' ? undefined : t('datasources.close')}
      >
        <DialogTitle>{t(initial ? 'datasources.form.editTitle' : 'datasources.create')}</DialogTitle>
        <DialogDescription>{t('datasources.form.description')}</DialogDescription>
        <form ref={formRef} noValidate onSubmit={save} className="mt-4 space-y-4">
          {showSummary && <InlineNotice tone="error">{t('datasources.form.validationSummary')}</InlineNotice>}
          {error !== null && <InlineNotice tone="error">{message(error)}</InlineNotice>}
          <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2" disabled={pending !== null}>
            {input('name')}
            <div className="space-y-1">
              <Label htmlFor={`${id}-kind`}>{t('datasources.fields.kind')}</Label>
              <NativeSelect id={`${id}-kind`}>
                <option value="postgresql">{t('datasources.kind.postgresql')}</option>
              </NativeSelect>
            </div>
            {input('host')}
            {input('port')}
            {input('database')}
            {input('username')}
            {input('password')}
            <div className="space-y-1">
              <Label htmlFor={`${id}-ssl`}>{t('datasources.fields.ssl')}</Label>
              <NativeSelect
                id={`${id}-ssl`}
                value={form.sslMode}
                onChange={(event) => change('sslMode', event.target.value as SourceForm['sslMode'])}
              >
                {sslModes.map((mode) => (
                  <option value={mode} key={mode}>{t(`datasources.ssl.${mode}`)}</option>
                ))}
              </NativeSelect>
            </div>
            <fieldset className="min-w-0 space-y-2 sm:col-span-2">
              <legend className="text-sm font-medium">{t('datasources.fields.schemas')}</legend>
              {form.schemas.map((row, index) => {
                const removeLabel = t('datasources.form.removeSchema', { index: index + 1 });
                return (
                  <div key={row.id} className="flex items-center gap-2">
                    <Input
                      aria-label={t('datasources.form.schemaName', { index: index + 1 })}
                      value={row.name}
                      maxLength={128}
                      onChange={(event) => change('schemas', form.schemas.map((item) =>
                        item.id === row.id ? { ...item, name: event.target.value } : item))}
                    />
                    <Button variant="ghost" size="icon" aria-label={removeLabel} title={removeLabel}
                      onClick={() => change('schemas', form.schemas.filter((item) => item.id !== row.id))}>
                      <Minus aria-hidden />
                    </Button>
                  </div>
                );
              })}
              <Button variant="secondary" size="sm" disabled={form.schemas.length >= 50}
                onClick={() => change('schemas', [...form.schemas, { id: nextRowId.current++, name: '' }])}>
                <Plus aria-hidden />{t('datasources.form.addSchema')}
              </Button>
            </fieldset>
            <div className="flex items-center gap-2 sm:col-span-2">
              <Label htmlFor={`${id}-samples`} className="cursor-pointer gap-2">
                <input
                  id={`${id}-samples`} role="switch" type="checkbox"
                  className="peer sr-only" checked={form.allowSamples} aria-checked={form.allowSamples}
                  onChange={(event) => change('allowSamples', event.target.checked)}
                />
                <span aria-hidden className="flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-muted px-0.5 text-muted-foreground peer-checked:justify-end peer-checked:bg-primary peer-checked:text-primary-foreground peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring">
                  <span className="size-3.5 rounded-full bg-current" />
                </span>
                {t('datasources.form.allowSamples')}
              </Label>
              <InfoTip>{t('datasources.form.samplesHelp')}</InfoTip>
            </div>
          </fieldset>
          {form.allowSamples && <InlineNotice tone="warning">{t('datasources.form.samplesWarning')}</InlineNotice>}
          {result && <ConnectionTestResult result={result} />}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button variant="secondary" loading={pending === 'test'} disabled={pending === 'save'} onClick={() => void run('test')}>
              {t('datasources.test.action')}
            </Button>
            <Button variant="ghost" className="ml-auto" onClick={onClose} disabled={pending === 'save'}>{t('datasources.cancel')}</Button>
            <Button type="submit" loading={pending === 'save'} disabled={pending === 'test'}>{t('datasources.form.save')}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
