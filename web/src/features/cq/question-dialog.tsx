import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input, inputClassName } from '@/components/ui/input';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Textarea } from '@/components/ui/textarea';

import { createQuestion, patchQuestion, type Create, type Question } from './api';
import { cqMessage } from './error-message';

const kinds = ['answerable', 'objects', 'number'] as const;
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

interface Props {
  ontologyId: string;
  question: Question | null;
  types: ReadonlyMap<string, string>;
  typeError: Error | null;
  retryTypes: () => void;
  onClose: () => void;
  onSaved: () => void;
  onRefresh: () => void;
}

export function QuestionDialog({ ontologyId, question, types, typeError, retryTypes, onClose, onSaved, onRefresh }: Props) {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState(question?.text ?? '');
  const [kind, setKind] = useState<Question['expect']['kind']>(question?.expect.kind ?? 'answerable');
  const [typeId, setTypeId] = useState(question?.expect.typeId ?? '');
  const [rawKeys, setKeys] = useState(question?.expect.keys.join('\n') ?? '');
  const [number, setNumber] = useState(question?.expect.number ?? '');
  const [tolerance, setTolerance] = useState(question?.expect.tolerance ?? '0');
  const [note, setNote] = useState(question?.note ?? '');
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const save = useMutation({
    mutationFn: (body: Create) => question
      ? patchQuestion(question.id, { ...body, revision: question.revision })
      : createQuestion(ontologyId, body),
    onSuccess: onSaved,
  });
  const keys = rawKeys.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const value = number.trim();
  const margin = tolerance.trim() || '0';
  const errors: Record<string, string> = {};
  if (!text.trim() || [...text.trim()].length > 500) errors.text = t('cq.validation.text');
  if ([...note].length > 1000) errors.note = t('cq.validation.note');
  if (kind === 'objects') {
    if (!types.has(typeId)) errors.type = t('cq.validation.type');
    if (keys.length > 100) errors.keys = t('cq.validation.keys');
  }
  if (kind === 'number') {
    if (!decimal.test(value)) errors.number = t('cq.validation.number');
    // The sign of a finite decimal depends on its coefficient, even below JS's numeric range.
    if (!decimal.test(margin) || (margin.startsWith('-') && /[1-9]/.test(margin.split(/e/i)[0]!))) {
      errors.tolerance = t('cq.validation.tolerance');
    }
  }
  const visibleErrors = Object.entries(errors).filter(([name]) => submitted || touched[name]);
  const attrs = (name: string) => ({
    'aria-invalid': Boolean(errors[name] && (submitted || touched[name])),
    onBlur: () => setTouched((old) => ({ ...old, [name]: true })),
  });
  const submit = () => {
    setSubmitted(true);
    if (Object.keys(errors).length || save.isPending) return;
    const expect: Create['expect'] = kind === 'objects' ? { kind, typeId, keys }
      : kind === 'number' ? { kind, number: value, tolerance: margin } : { kind };
    save.mutate({ text: text.trim(), expect, ...(note || question?.note ? { note } : {}) });
  };
  const stale = isApiError(save.error) && save.error.code === 'cq.stale';
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !save.isPending) onClose(); }}>
      <DialogContent closeLabel={t('common.close')} className="max-h-[90dvh] overflow-y-auto">
        <DialogTitle>{t(question ? 'cq.edit' : 'cq.create')}</DialogTitle>
        <form noValidate className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); submit(); }}>
          {visibleErrors.length > 0 && <InlineNotice tone="error"><ul>
            {visibleErrors.map(([key, message]) => <li key={key}>{message}</li>)}
          </ul></InlineNotice>}
          {save.error && <InlineNotice tone="error" action={stale &&
            <Button variant="secondary" size="sm" onClick={onRefresh}>{t('ontologyPage.form.reload')}</Button>}>
            {cqMessage(i18n, save.error)}
          </InlineNotice>}
          <label className="block space-y-1 text-sm font-medium">
            <span>{t('cq.text')} *</span>
            <Textarea required value={text} onChange={(e) => setText(e.target.value)} {...attrs('text')} />
          </label>
          <SegmentedControl legend={t('cq.expectation')} value={kind} onValueChange={setKind}
            options={kinds.map((value) => ({ value, label: t(`cq.kinds.${value}`) }))} />
          {kind === 'objects' && <>
            {typeError !== null && <InlineNotice tone="error" action={
              <Button size="sm" variant="secondary" onClick={retryTypes}>{t('common.retry')}</Button>
            }>{cqMessage(i18n, typeError)}</InlineNotice>}
            <label className="block space-y-1 text-sm font-medium">
              <span>{t('cq.type')} *</span>
              <select required className={inputClassName} value={typeId} onChange={(e) => setTypeId(e.target.value)} {...attrs('type')}>
                <option value="">{t('cq.selectType')}</option>
                {typeId && !types.has(typeId) && <option value={typeId} disabled>{t('review.unknownType')}</option>}
                {Array.from(types, ([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label className="block space-y-1 text-sm font-medium">
              <span>{t('cq.keys')}</span>
              <Textarea value={rawKeys} aria-describedby="cq-key-format" onChange={(e) => setKeys(e.target.value)} {...attrs('keys')} />
            </label>
            <p id="cq-key-format" className="text-xs text-muted-foreground">{t('cq.keyFormat')}</p>
          </>}
          {kind === 'number' && <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1 text-sm font-medium">
              <span>{t('cq.number')} *</span>
              <Input required inputMode="decimal" value={number} onChange={(e) => setNumber(e.target.value)} {...attrs('number')} />
            </label>
            <label className="block space-y-1 text-sm font-medium">
              <span>{t('cq.tolerance')}</span>
              <Input inputMode="decimal" value={tolerance} onChange={(e) => setTolerance(e.target.value)} {...attrs('tolerance')} />
            </label>
          </div>}
          <label className="block space-y-1 text-sm font-medium">
            <span>{t('cq.note')}</span>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} {...attrs('note')} />
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" disabled={save.isPending} onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={save.isPending} disabled={stale}>{t('ontologyPage.edit.save')}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
