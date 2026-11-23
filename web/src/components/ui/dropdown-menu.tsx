import { Menu } from '@base-ui/react/menu';
import { Check } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';

import { cn } from '@/lib/cn';

export const DropdownMenu = Menu.Root;
export const DropdownMenuTrigger = Menu.Trigger;
export const DropdownMenuRadioGroup = Menu.RadioGroup;
export const DropdownMenuGroup = Menu.Group;

interface ContentProps {
  children: ReactNode;
  align?: 'start' | 'center' | 'end';
  side?: 'top' | 'bottom' | 'left' | 'right';
  sideOffset?: number;
  className?: string;
}

export function DropdownMenuContent({ children, align = 'end', side = 'bottom', sideOffset = 8, className }: ContentProps) {
  return (
    <Menu.Portal>
      <Menu.Positioner align={align} side={side} sideOffset={sideOffset} className="z-50 outline-none">
        <Menu.Popup
          className={cn(
            'min-w-48 rounded-xl border border-border bg-card p-1.5 text-foreground shadow-popover outline-none',
            'origin-(--transform-origin) transition-[opacity,scale] duration-150',
            'data-[starting-style]:scale-95 data-[starting-style]:opacity-0 data-[ending-style]:scale-95 data-[ending-style]:opacity-0',
            className,
          )}
        >
          {children}
        </Menu.Popup>
      </Menu.Positioner>
    </Menu.Portal>
  );
}

const itemClassName = cn(
  'flex h-9 cursor-default select-none items-center gap-2.5 rounded-lg px-2.5 text-sm outline-none',
  'data-[highlighted]:bg-muted data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
  '[&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground',
);

type ItemProps = Omit<ComponentProps<typeof Menu.Item>, 'className'> & { className?: string };

export function DropdownMenuItem({ className, ...props }: ItemProps) {
  return <Menu.Item className={cn(itemClassName, className)} {...props} />;
}

type RadioItemProps = Omit<ComponentProps<typeof Menu.RadioItem>, 'className'> & { className?: string };

export function DropdownMenuRadioItem({ className, children, ...props }: RadioItemProps) {
  return (
    <Menu.RadioItem className={cn(itemClassName, 'pr-8 relative', className)} {...props}>
      {children}
      <Menu.RadioItemIndicator className="absolute right-2.5 flex items-center [&_svg]:text-primary-strong">
        <Check aria-hidden />
      </Menu.RadioItemIndicator>
    </Menu.RadioItem>
  );
}

export function DropdownMenuLabel({ className, ...props }: Omit<ComponentProps<typeof Menu.GroupLabel>, 'className'> & { className?: string }) {
  return <Menu.GroupLabel className={cn('px-2.5 pb-1 pt-1.5 text-xs font-medium text-muted-foreground', className)} {...props} />;
}

export function DropdownMenuSeparator({ className }: { className?: string }) {
  return <Menu.Separator className={cn('-mx-1.5 my-1.5 h-px bg-border', className)} />;
}
