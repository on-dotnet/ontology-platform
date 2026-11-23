import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/cn';

export type StateTone = 'primary' | 'secondary' | 'success' | 'warning' | 'info' | 'error';

export const toneIconClassName: Record<StateTone, string> = {
  primary: 'bg-primary-soft text-primary-strong',
  secondary: 'bg-secondary-soft text-secondary-strong',
  success: 'bg-success-soft text-success-strong',
  warning: 'bg-warning-soft text-warning-strong',
  info: 'bg-info-soft text-info-strong',
  error: 'bg-error-soft text-error-strong',
};

interface EmptyStateProps {
  icon: LucideIcon;
  title: ReactNode;
  /** One sentence on what will appear here or what to do next. */
  description?: ReactNode;
  /** The next-step button; at most one more, secondary, for another common way to start (ui-guidelines §5). */
  action?: ReactNode;
  /** Small label above the title, e.g. "Coming soon". */
  badge?: ReactNode;
  tone?: StateTone;
  /** Heading element for the title; `h1` when the state is the whole page. */
  headingLevel?: 'h1' | 'h2' | 'h3';
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  badge,
  tone = 'primary',
  headingLevel: Heading = 'h2',
  className,
}: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center px-6 py-14 text-center', className)}>
      <div className={cn('mb-5 flex size-16 items-center justify-center rounded-2xl', toneIconClassName[tone])}>
        <Icon className="size-7" aria-hidden strokeWidth={1.75} />
      </div>
      {badge ? (
        <Badge tone="secondary" className="mb-3">
          {badge}
        </Badge>
      ) : null}
      <Heading className="text-base font-semibold text-foreground">{title}</Heading>
      {description ? <p className="mt-1.5 max-w-md text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
