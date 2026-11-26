import { Tabs as BaseTabs } from '@base-ui/react/tabs';
import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

export const Tabs = BaseTabs.Root;
export const TabsPanel = BaseTabs.Panel;

type ListProps = Omit<ComponentProps<typeof BaseTabs.List>, 'className'> & { className?: string };

export function TabsList({ className, ...props }: ListProps) {
  return <BaseTabs.List className={cn('flex gap-1 border-b border-border', className)} {...props} />;
}

type TabProps = Omit<ComponentProps<typeof BaseTabs.Tab>, 'className'> & { className?: string };

export function TabsTrigger({ className, ...props }: TabProps) {
  return (
    <BaseTabs.Tab
      className={cn(
        'rounded-t-lg border-b-2 border-transparent px-4 py-2 text-sm font-medium text-muted-foreground',
        'hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring aria-selected:border-primary aria-selected:text-primary-strong',
        className,
      )}
      {...props}
    />
  );
}
