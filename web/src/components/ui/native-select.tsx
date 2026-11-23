import { ChevronDown } from 'lucide-react';
import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

import { inputClassName } from './input';

interface NativeSelectProps extends ComponentProps<'select'> {
  containerClassName?: string;
}

/** Styled native select: keyboard, screen reader and mobile behavior come from the platform. */
export function NativeSelect({ className, containerClassName, children, ...props }: NativeSelectProps) {
  return (
    <div className={cn('relative min-w-0', containerClassName)}>
      <select className={cn(inputClassName, 'cursor-pointer appearance-none pr-9', className)} {...props}>
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
    </div>
  );
}
