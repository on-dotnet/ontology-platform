import { Plus, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';

type Property = components['schemas']['ObjectProperty'];
type Filter = components['schemas']['Filter'];
type Scalar = components['schemas']['FilterValue'];

interface FilterEditorProps {
  properties: Property[];
  filters: Filter[];
  onChange: (filters: Filter[]) => void;
  onExpandedChange?: (expanded: boolean) => void;
}

const maxFilters = 10;
const maxValues = 100;

function draftFor(property: Property, op = property.ops[0]) {
  if (!op) return null;
  return { propertyId: property.propertyId, op, raw: property.datatype === 'boolean' ? 'true' : '' };
}

type Parsed = { filter: Filter } | { error: string };

function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000-')) return false;
  const date = new Date(value);
  // Date normalizes some impossible days into the next month.
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function parseFilter(property: Property, op: Filter['op'], raw: string): Parsed {
  const condition = { propertyId: property.propertyId, op };
  if (op === 'isNull' || op === 'notNull') return { filter: condition };
  const entries = op === 'in' ? raw.split(/\r?\n/).filter((line) => line !== '') : [raw];
  if (!entries.length || raw === '') return { error: 'explore.filter.required' };
  if (entries.length > maxValues) return { error: 'explore.filter.tooManyValues' };

  const values: Scalar[] = [];
  for (const entry of entries) {
    const trimmed = entry.trim();
    switch (property.datatype) {
      case 'integer': {
        if (!/^[+-]?\d+$/.test(trimmed)) return { error: 'explore.filter.invalidInteger' };
        const number = Number(trimmed);
        values.push(Number.isSafeInteger(number) ? number : trimmed);
        break;
      }
      case 'decimal':
        if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(trimmed)) {
          return { error: 'explore.filter.invalidDecimal' };
        }
        values.push(trimmed);
        break;
      case 'boolean':
        values.push(entry === 'true');
        break;
      case 'date':
        if (!isCalendarDate(entry)) return { error: 'explore.filter.invalidDate' };
        values.push(entry);
        break;
      default:
        values.push(entry);
    }
  }
  return { filter: { ...condition, value: op === 'in' ? values : values[0] } };
}

export function FilterEditor({ properties, filters, onChange, onExpandedChange }: FilterEditorProps) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState<ReturnType<typeof draftFor>>(null);
  const [touched, setTouched] = useState(false);
  const available = properties.filter((property) => property.ops.length > 0);
  const selected = available.find((property) => property.propertyId === draft?.propertyId);
  const atLimit = filters.length >= maxFilters;
  const expanded = !!draft && !!selected && selected.ops.includes(draft.op) && !atLimit;
  useEffect(() => { onExpandedChange?.(expanded); }, [expanded, onExpandedChange]);
  const parsed = expanded ? parseFilter(selected, draft.op, draft.raw) : null;
  const error = touched && parsed && 'error' in parsed ? parsed.error : null;
  const valueId = `${id}-value`;
  const errorId = `${id}-error`;

  function select(property: Property, op?: Filter['op']) {
    setDraft(draftFor(property, op));
    setTouched(false);
  }

  function formatValue(value: Scalar) {
    if (typeof value === 'boolean') return t(value ? 'explore.yes' : 'explore.no');
    return String(value);
  }

  const valueProps = {
    id: valueId,
    value: draft?.raw ?? '',
    required: true,
    'aria-invalid': !!error,
    'aria-describedby': error ? errorId : undefined,
    onBlur: () => setTouched(true),
  };
  const datatype = selected?.datatype;
  const placeholder = datatype === 'date' || datatype === 'dateTime'
    ? t(`explore.filter.${datatype}Example`) : undefined;
  function setValue(raw: string) {
    if (draft) setDraft({ ...draft, raw });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {filters.map((filter, index) => {
          const label = properties.find((property) => property.propertyId === filter.propertyId)?.label;
          const { value } = filter;
          const text = Array.isArray(value)
            ? new Intl.ListFormat(i18n.language, { type: 'disjunction' }).format(value.map(formatValue))
            : value === null || value === undefined ? '' : formatValue(value);
          const summary = [label, t(`explore.op.${filter.op}`), text].filter(Boolean).join(' ');
          const remove = t('explore.filter.remove', { filter: summary });
          return (
            <Button
              key={index} variant="soft" size="sm" className="max-w-full rounded-md"
              aria-label={remove} title={remove} onClick={() => onChange(filters.filter((_, i) => i !== index))}
            >
              <span className="truncate">{summary}</span><X aria-hidden />
            </Button>
          );
        })}
        <Button
          ref={toggle} variant="secondary" size="sm" disabled={atLimit || !available.length}
          aria-expanded={expanded} aria-controls={expanded ? id : undefined}
          aria-describedby={atLimit ? `${id}-limit` : undefined}
          onClick={() => {
            if (expanded) setDraft(null);
            else if (available[0]) select(available[0]);
          }}
        >
          {expanded ? t('explore.filter.cancel') : <><Plus aria-hidden />{t('explore.filter.add')}</>}
        </Button>
        {atLimit && <span id={`${id}-limit`} className="text-sm text-muted-foreground">{t('explore.filter.limit')}</span>}
      </div>
      {expanded && (
        <form
          id={id} noValidate className="space-y-2 rounded-lg border border-border bg-card p-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!parsed || !('filter' in parsed)) {
              setTouched(true);
              event.currentTarget.querySelector<HTMLElement>('[name="value"]')?.focus();
              return;
            }
            onChange([...filters, parsed.filter]);
            setDraft(null);
            toggle.current?.focus();
          }}
        >
          {error && <p id={errorId} role="alert" className="text-sm text-error-strong">{t(error)}</p>}
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1">
              <Label htmlFor={`${id}-property`} required>{t('explore.filter.property')}</Label>
              <NativeSelect
                id={`${id}-property`} required value={selected.propertyId}
                onChange={(event) => {
                  const next = available.find((property) => property.propertyId === event.target.value);
                  if (next) select(next);
                }}
              >
                {available.map((property) => <option key={property.propertyId} value={property.propertyId}>{property.label}</option>)}
              </NativeSelect>
            </div>
            <div className="grid gap-1">
              <Label htmlFor={`${id}-operator`} required>{t('explore.filter.operator')}</Label>
              <NativeSelect
                id={`${id}-operator`} required value={draft.op}
                onChange={(event) => {
                  const op = selected.ops.find((item) => item === event.target.value);
                  if (op) select(selected, op);
                }}
              >
                {selected.ops.map((op) => <option key={op} value={op}>{t(`explore.op.${op}`)}</option>)}
              </NativeSelect>
            </div>
            {draft.op !== 'isNull' && draft.op !== 'notNull' && (
              <div className="grid min-w-0 flex-auto gap-1">
                <Label htmlFor={valueId} required>{t(draft.op === 'in' ? 'explore.filter.values' : 'explore.filter.value')}</Label>
                {draft.op === 'in' ? (
                  <Textarea {...valueProps} name="value" placeholder={placeholder} onChange={(event) => setValue(event.target.value)} />
                ) : selected.datatype === 'boolean' ? (
                  <NativeSelect {...valueProps} name="value" onChange={(event) => setValue(event.target.value)}>
                    <option value="true">{t('explore.yes')}</option>
                    <option value="false">{t('explore.no')}</option>
                  </NativeSelect>
                ) : (
                  <Input
                    {...valueProps} name="value" type="text" placeholder={placeholder}
                    onChange={(event) => setValue(event.target.value)}
                  />
                )}
              </div>
            )}
            <Button type="submit">{t('explore.filter.apply')}</Button>
          </div>
        </form>
      )}
    </div>
  );
}
