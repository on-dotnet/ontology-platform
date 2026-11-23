import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

export function Kbd({ className, ...props }: ComponentProps<'kbd'>) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 items-center rounded border border-current/25 px-1.5 font-sans text-[0.6875rem] font-medium',
        className,
      )}
      {...props}
    />
  );
}
