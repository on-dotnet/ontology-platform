import { Plus, X } from 'lucide-react';
import { type FocusEvent, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { checkDateValue, joinDateValue } from './date-value';

interface DateValueFieldsProps {
  /** One value per line, the same draft text the other `in` filters use. */
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  multiple: boolean;
  withTime: boolean;
  timeRequired: boolean;
  maxValues: number;
  invalid: boolean;
  errorId: string;
}

/** Stable, so React calls it only when a newly added row's input first receives it. */
function focusOnAttach(node: HTMLInputElement | null) {
  node?.focus();
}

export function DateValueFields({
  value, onChange, onBlur, multiple, withTime, timeRequired, maxValues, invalid, errorId,
}: DateValueFieldsProps) {
  const { t } = useTranslation();
  const id = useId();
  const list = useRef<HTMLDivElement>(null);
  const lines = value.split('\n');
  const [added, setAdded] = useState(false);
  const label = t('explore.filter.value');
  const hintId = `${id}-hint`;

  function replace(index: number, date: string, time: string) {
    onChange(lines.map((line, i) => i === index ? joinDateValue(date, time) : line).join('\n'));
  }

  function remove(index: number) {
    // The clicked button may unmount, so focus moves to the row that ends up in this place.
    list.current?.querySelectorAll<HTMLInputElement>('input[type="date"]')[Math.min(index, lines.length - 2)]?.focus();
    setAdded(false);
    onChange(lines.filter((_, i) => i !== index).join('\n'));
  }

  const checked = lines.map((line) => checkDateValue(line, withTime, timeRequired));
  // The form focuses the input named `value` when it refuses a submission.
  const firstBad = checked.findIndex((entry) => entry.badDate || entry.badTime);

  const rows = checked.map(({ date, time, badDate, badTime }, index) => {
    const position = index + 1;
    const dateInput = (
      <Input
        id={multiple ? undefined : `${id}-date`} name={index === firstBad && badDate ? 'value' : undefined} type="date"
        min="0001-01-01" max="9999-12-31" required className="w-44"
        aria-label={multiple ? t('explore.filter.datePosition', { position }) : undefined}
        aria-invalid={invalid && badDate} aria-describedby={invalid && badDate ? errorId : undefined}
        ref={added && index === lines.length - 1 ? focusOnAttach : undefined} value={date}
        onChange={(event) => replace(index, event.target.value, time)}
      />
    );
    const timeInput = withTime && (
      <Input
        id={multiple ? undefined : `${id}-time`} name={index === firstBad && !badDate ? 'value' : undefined}
        type="text" required={timeRequired} className="w-56"
        aria-label={multiple ? t('explore.filter.timePosition', { position }) : undefined}
        aria-invalid={invalid && badTime}
        aria-describedby={invalid && badTime ? `${hintId} ${errorId}` : hintId} value={time}
        onChange={(event) => replace(index, date, event.target.value)}
      />
    );
    if (!multiple) {
      return (
        <div key={index} className="flex flex-wrap gap-3">
          <div className="grid gap-1">
            <Label htmlFor={`${id}-date`} required>{label}</Label>
            {dateInput}
          </div>
          {withTime && <div className="grid gap-1">
            <Label htmlFor={`${id}-time`} required={timeRequired}>{t('explore.filter.time')}</Label>
            {timeInput}
          </div>}
        </div>
      );
    }
    return (
      <div key={index} className="flex flex-wrap items-center gap-2">
        {dateInput}
        {timeInput}
        {lines.length > 1 && <Button
          variant="ghost" size="sm" aria-label={t('explore.filter.removeValue', { position })}
          title={t('explore.filter.removeValue', { position })} onClick={() => remove(index)}
        >
          <X aria-hidden />
        </Button>}
      </div>
    );
  });
  const hint = withTime && (
    <p id={hintId} className="text-sm text-muted-foreground">
      {t(timeRequired ? 'explore.filter.timeHint' : 'explore.filter.optionalTimeHint')}
    </p>
  );
  const leaving = (event: FocusEvent<HTMLElement>) => {
    // Moving between the date and the time of one value is not leaving the field.
    if (!event.currentTarget.contains(event.relatedTarget)) onBlur();
  };

  if (!multiple) return <div className="grid min-w-0 gap-1" onBlur={leaving}>{rows}{hint}</div>;
  return (
    <fieldset className="grid min-w-0 gap-1" onBlur={leaving}>
      <legend className="mb-1 text-sm font-medium">{label}<span className="ml-1 text-error-strong" aria-hidden>*</span></legend>
      {/* Column titles for sighted users; each input carries its own numbered name. */}
      {withTime && <div className="flex gap-2 px-1 text-sm text-muted-foreground" aria-hidden>
        <span className="w-44">{t('explore.filter.date')}</span>
        <span className="w-56">{t('explore.filter.time')}</span>
      </div>}
      {/* The padding keeps focus rings inside the scrolling area. */}
      <div ref={list} className="max-h-60 space-y-2 overflow-y-auto p-1">{rows}</div>
      <div>
        <Button
          variant="secondary" size="sm" disabled={lines.length >= maxValues}
          onClick={() => { setAdded(true); onChange(`${value}\n`); }}
        >
          <Plus aria-hidden />{t('explore.filter.addValue')}
        </Button>
      </div>
      {hint}
    </fieldset>
  );
}
