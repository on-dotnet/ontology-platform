import { useId, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface SegmentedControlProps<T extends string> {
  legend: ReactNode;
  value: T;
  options: readonly SegmentedOption<T>[];
  onValueChange: (value: T) => void;
  /** Keeps the legend for screen readers only, e.g. in a toolbar where the options speak for themselves. */
  hideLegend?: boolean;
  className?: string;
}

/** A small set of mutually exclusive choices, built on native radios (arrow keys work out of the box). */
export function SegmentedControl<T extends string>({
  legend,
  value,
  options,
  onValueChange,
  hideLegend = false,
  className,
}: SegmentedControlProps<T>) {
  const name = useId();
  return (
    <fieldset className={cn('m-0 min-w-0 border-0 p-0', className)}>
      <legend className={hideLegend ? 'sr-only' : 'mb-2 p-0 text-sm font-medium text-foreground'}>{legend}</legend>
      <div className="inline-flex flex-wrap gap-1 rounded-lg border border-border bg-muted p-1">
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              'relative flex h-8 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors',
              'hover:text-foreground [&_svg]:size-4',
              'has-checked:bg-card has-checked:text-foreground has-checked:shadow-sm',
              'has-focus-visible:outline-2 has-focus-visible:outline-offset-1 has-focus-visible:outline-ring',
            )}
          >
            <input
              type="radio"
              className="sr-only"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onValueChange(option.value)}
            />
            {option.icon}
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
