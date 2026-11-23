import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/cn';

const SLOW_AFTER_MS = 10_000;

interface LoadingStateProps {
  /** Skeleton shape matching the final layout. */
  variant?: 'cards' | 'list' | 'detail';
  /** Shown after 10 s as a "cancel" button when the work can be cancelled. */
  onCancel?: () => void;
  className?: string;
}

/** Skeleton placeholder; after 10 s it says the work is still in progress (ui-guidelines §5). */
export function LoadingState({ variant = 'list', onCancel, className }: LoadingStateProps) {
  const { t } = useTranslation();
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div role="status" aria-live="polite" aria-busy className={cn('space-y-4', className)}>
      <span className="sr-only">{t('common.loading')}</span>
      {variant === 'cards' ? (
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((key) => (
            <Skeleton key={key} className="h-32 rounded-xl" />
          ))}
        </div>
      ) : null}
      {variant === 'list' ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((key) => (
            <Skeleton key={key} className="h-10 rounded-lg" />
          ))}
        </div>
      ) : null}
      {variant === 'detail' ? (
        <div className="space-y-3">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : null}
      {slow ? (
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>{t('common.stillWorking')}</span>
          {onCancel ? (
            <Button variant="secondary" size="sm" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
