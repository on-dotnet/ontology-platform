import { Dialog as BaseDialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { buttonVariants } from './button';

export const Dialog = BaseDialog.Root;
export const DialogTrigger = BaseDialog.Trigger;
export const DialogClose = BaseDialog.Close;

const backdropClassName = cn(
  'fixed inset-0 z-40 bg-overlay transition-opacity duration-200',
  'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
);

interface ContentProps {
  children: ReactNode;
  className?: string;
  /** Accessible label of the close button; omit to hide the button. */
  closeLabel?: string;
}

/** Centered modal dialog (confirmations, short forms). */
export function DialogContent({ children, className, closeLabel }: ContentProps) {
  return (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className={backdropClassName} />
      <BaseDialog.Popup
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2',
          'rounded-xl border border-border bg-card p-6 text-foreground shadow-popover outline-none',
          'transition-[opacity,scale] duration-200 data-[starting-style]:scale-95 data-[starting-style]:opacity-0',
          'data-[ending-style]:scale-95 data-[ending-style]:opacity-0',
          className,
        )}
      >
        {children}
        {closeLabel ? <CloseButton label={closeLabel} className="absolute right-3 top-3" /> : null}
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  );
}

interface SheetContentProps extends ContentProps {
  side?: 'left' | 'right';
}

/** Panel sliding in from a screen edge (the navigation drawer on narrow screens). */
export function SheetContent({ children, className, side = 'left', closeLabel }: SheetContentProps) {
  return (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className={backdropClassName} />
      <BaseDialog.Popup
        className={cn(
          'fixed inset-y-0 z-50 flex w-72 max-w-[85vw] flex-col bg-card text-foreground shadow-popover outline-none',
          'transition-transform duration-200 ease-out',
          side === 'left'
            ? 'left-0 border-r border-border data-[starting-style]:-translate-x-full data-[ending-style]:-translate-x-full'
            : 'right-0 border-l border-border data-[starting-style]:translate-x-full data-[ending-style]:translate-x-full',
          className,
        )}
      >
        {children}
        {closeLabel ? <CloseButton label={closeLabel} className="absolute right-3 top-3" /> : null}
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  );
}

function CloseButton({ label, className }: { label: string; className?: string }) {
  return (
    <BaseDialog.Close aria-label={label} className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }), className)}>
      <X aria-hidden />
    </BaseDialog.Close>
  );
}

export function DialogTitle({ className, ...props }: Omit<ComponentProps<typeof BaseDialog.Title>, 'className'> & { className?: string }) {
  return <BaseDialog.Title className={cn('text-lg font-semibold', className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: Omit<ComponentProps<typeof BaseDialog.Description>, 'className'> & { className?: string }) {
  return <BaseDialog.Description className={cn('mt-1 text-sm text-muted-foreground', className)} {...props} />;
}
