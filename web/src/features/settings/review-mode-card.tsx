import { ClipboardCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { usePlatformSettings } from '@/features/ontologies/api';

/** Settings card: the review mode the platform runs in (`OP_REVIEW_MODE`), read-only. */
export function ReviewModeCard() {
  const { t } = useTranslation();
  const query = usePlatformSettings();
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-strong">
          <ClipboardCheck className="size-4.5" aria-hidden />
        </span>
        <CardTitle>{t('settings.reviewTitle')}</CardTitle>
      </CardHeader>
      <CardContent>
        <QueryState
          query={query}
          loading={
            <div role="status" aria-busy>
              <span className="sr-only">{t('common.loading')}</span>
              <Skeleton className="h-5 w-40" />
            </div>
          }
        >
          {({ reviewMode }) => (
            <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-sm">
              <dt className="text-muted-foreground">{t('settings.reviewModeLabel')}</dt>
              <dd className="flex items-center gap-0.5">
                <Badge tone="primary">{t(`settings.reviewModes.${reviewMode}`)}</Badge>
                <InfoTip label={t('settings.reviewModeInfoLabel')}>{t('settings.reviewModeInfo')}</InfoTip>
              </dd>
            </dl>
          )}
        </QueryState>
      </CardContent>
    </Card>
  );
}
