import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';
import type { ComponentProps, ReactElement, ReactNode } from 'react';

import { cn } from '@/lib/cn';

export const TooltipProvider = BaseTooltip.Provider;

type Side = 'top' | 'bottom' | 'left' | 'right';

export const tooltipPopupClassName = cn(
  'max-w-72 rounded-lg bg-foreground px-3 py-2 text-xs leading-relaxed font-medium text-background shadow-popover',
  'origin-(--transform-origin) transition-[opacity,scale] duration-150',
  'data-[starting-style]:scale-95 data-[starting-style]:opacity-0 data-[ending-style]:scale-95 data-[ending-style]:opacity-0',
);

interface TooltipContentProps extends Omit<ComponentProps<typeof BaseTooltip.Popup>, 'className'> {
  side?: Side;
  sideOffset?: number;
  className?: string;
}

/** Positioned bubble; render inside a `BaseTooltip.Root`. */
export function TooltipContent({ side = 'top', sideOffset = 8, className, children, ...props }: TooltipContentProps) {
  return (
    <BaseTooltip.Portal>
      <BaseTooltip.Positioner side={side} sideOffset={sideOffset} className="z-60">
        <BaseTooltip.Popup role="tooltip" className={cn(tooltipPopupClassName, className)} {...props}>
          {children}
        </BaseTooltip.Popup>
      </BaseTooltip.Positioner>
    </BaseTooltip.Portal>
  );
}

interface TooltipProps {
  /** Text shown on hover and keyboard focus. */
  content: ReactNode;
  /** A single focusable element (button, link) that receives the trigger props. */
  children: ReactElement;
  side?: Side;
  /** Hides the tooltip without changing the tree (e.g. labels already visible). */
  disabled?: boolean;
}

/** Hover/focus label for an element, typically an icon-only button (ui-guidelines §8). */
export function Tooltip({ content, children, side = 'top', disabled = false }: TooltipProps) {
  return (
    <BaseTooltip.Root disabled={disabled}>
      <BaseTooltip.Trigger render={children} />
      <TooltipContent side={side}>{content}</TooltipContent>
    </BaseTooltip.Root>
  );
}
