import { Cpu } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { WarnTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { aiHealth, isAiDegraded, useAiStatus, type AiHealth } from './api';

/** Yellow banner when AI analysis is unavailable, saying what still works (ui-guidelines §7). */
export function AiStatusNotice({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { data } = useAiStatus();
  if (!data) return null;
  const health = aiHealth(data);
  if (!isAiDegraded(health)) return null;
  return (
    <InlineNotice tone="warning" title={t(`ai.notice.${health}.title`)} className={className}>
      {t(`ai.notice.${health}.description`)}
    </InlineNotice>
  );
}

/** Top-bar "!" next to the assistant button, shown only while AI analysis is unavailable. */
export function AiStatusIndicator() {
  const { t } = useTranslation();
  const { data } = useAiStatus();
  if (!data) return null;
  const health = aiHealth(data);
  if (!isAiDegraded(health)) return null;
  return (
    <WarnTip label={t(`ai.notice.${health}.title`)} side="bottom" className="size-8">
      {t(`ai.notice.${health}.description`)}
    </WarnTip>
  );
}

const healthTone: Record<AiHealth, BadgeTone> = {
  available: 'success',
  unreachable: 'warning',
  not_configured: 'warning',
  unknown: 'neutral',
};

/** Settings card: whether the model service is usable and which model is configured. No address or key. */
export function AiServiceCard() {
  const { t } = useTranslation();
  const query = useAiStatus();
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-info-soft text-info-strong">
          <Cpu className="size-4.5" aria-hidden />
        </span>
        <CardTitle>{t('settings.aiTitle')}</CardTitle>
      </CardHeader>
      <CardContent>
        <QueryState
          query={query}
          loading={
            <div className="space-y-3" role="status" aria-busy>
              <span className="sr-only">{t('common.loading')}</span>
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-5 w-56" />
            </div>
          }
        >
          {(status) => {
            const health = aiHealth(status);
            return (
              <div className="space-y-4">
                <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-sm">
                  <dt className="text-muted-foreground">{t('settings.aiStatus')}</dt>
                  <dd>
                    <Badge tone={healthTone[health]}>{t(`ai.health.${health}`)}</Badge>
                  </dd>
                  <dt className="text-muted-foreground">{t('settings.aiModel')}</dt>
                  <dd className="font-medium text-foreground">{status.model ?? t('settings.aiModelNone')}</dd>
                </dl>
                {isAiDegraded(health) ? (
                  <InlineNotice tone="warning" title={t(`ai.notice.${health}.title`)}>
                    {t(`ai.notice.${health}.description`)}
                  </InlineNotice>
                ) : null}
              </div>
            );
          }}
        </QueryState>
      </CardContent>
    </Card>
  );
}
