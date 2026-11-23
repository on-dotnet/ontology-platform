import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

/** Compact data table (ui-guidelines §9): 40px rows, sticky header, numbers right-aligned via `numeric`. */
export function Table({ className, ...props }: ComponentProps<'table'>) {
  return (
    // Horizontal scrolling only on narrow screens, so the sticky header follows the page scroll elsewhere.
    <div className="max-md:overflow-x-auto">
      <table className={cn('w-full border-collapse text-sm', className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: ComponentProps<'thead'>) {
  return <thead className={cn('sticky top-0 z-10 bg-muted', className)} {...props} />;
}

export function TableBody(props: ComponentProps<'tbody'>) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<'tr'>) {
  return <tr className={cn('border-t border-border transition-colors hover:bg-muted/50', className)} {...props} />;
}

interface CellProps {
  numeric?: boolean;
}

export function TableHead({ className, numeric = false, ...props }: ComponentProps<'th'> & CellProps) {
  return (
    <th
      scope="col"
      className={cn(
        'h-10 whitespace-nowrap px-4 text-xs font-semibold text-muted-foreground first:rounded-tl-xl last:rounded-tr-xl',
        numeric ? 'text-right' : 'text-left',
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({ className, numeric = false, ...props }: ComponentProps<'td'> & CellProps) {
  return (
    <td className={cn('h-10 px-4 py-2 align-middle', numeric ? 'text-right tabular-nums' : 'text-left', className)} {...props} />
  );
}
