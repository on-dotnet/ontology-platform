import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { useErrorMessage } from '@/i18n/error-message';

interface ErrorStateProps {
  error: unknown;
  /** Defaults to a generic "could not be loaded". */
  title?: string;
  onRetry?: () => void;
  className?: string;
}

/** Red banner with cause, advice and retry; technical details stay collapsed (ui-guidelines §5). */
export function ErrorState({ error, title, onRetry, className }: ErrorStateProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const details = isApiError(error) ? `${error.code} · HTTP ${error.status || '—'}` : undefined;

  return (
    <InlineNotice
      tone="error"
      title={title ?? t('states.errorTitle')}
      className={className}
      action={
        onRetry || details ? (
          <div className="space-y-2">
            {onRetry ? (
              <Button variant="secondary" size="sm" onClick={onRetry}>
                <RefreshCw aria-hidden />
                {t('common.retry')}
              </Button>
            ) : null}
            {details ? (
              <details className="text-xs text-muted-foreground">
                <summary className="w-fit cursor-pointer select-none rounded hover:text-foreground">
                  {t('common.technicalDetails')}
                </summary>
                <code className="mt-1 block font-mono">{details}</code>
              </details>
            ) : null}
          </div>
        ) : undefined
      }
    >
      {message(error)}
    </InlineNotice>
  );
}
