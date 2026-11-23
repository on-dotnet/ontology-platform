import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

interface LabelProps extends ComponentProps<'label'> {
  /** Appends the required marker `*` after the label text (ui-guidelines §8). */
  required?: boolean;
}

export function Label({ className, required = false, children, ...props }: LabelProps) {
  return (
    <label className={cn('inline-flex items-center gap-1 text-sm font-medium text-foreground', className)} {...props}>
      {children}
      {required ? (
        <span className="text-error-strong" aria-hidden>
          *
        </span>
      ) : null}
    </label>
  );
}
