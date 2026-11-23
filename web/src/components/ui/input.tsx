import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

export const inputClassName = cn(
  'h-10 w-full min-w-0 rounded-lg border border-border bg-card px-3 text-sm text-foreground transition-colors',
  'placeholder:text-muted-foreground',
  'outline-none focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary/30',
  'aria-invalid:border-error aria-invalid:focus-visible:outline-error/30',
  'disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-70',
);

export function Input({ className, type = 'text', ...props }: ComponentProps<'input'>) {
  return <input type={type} className={cn(inputClassName, className)} {...props} />;
}
