import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ForbiddenState } from '@/components/states/forbidden-state';
import { InlineNotice } from '@/components/feedback/inline-notice';

import type { ReviewAssist } from './api';

export function AssistRequestButton({ assist, canRequest, pending, onRequest }: {
  assist: ReviewAssist | null;
  canRequest: boolean;
  pending: boolean;
  onRequest: () => void;
}) {
  const { t } = useTranslation();
  const runningSince = assist?.status === 'queued' || assist?.status === 'running' ? assist.createdAt : null;
  const [slowSince, setSlowSince] = useState<string | null>(null);
  useEffect(() => {
    if (runningSince === null) return;
    const remaining = Math.max(0, Date.parse(runningSince) + 10_000 - Date.now());
    const timer = window.setTimeout(() => setSlowSince(runningSince), remaining);
    return () => window.clearTimeout(timer);
  }, [runningSince]);

  return (
    <>
      {canRequest ? (
        <Button variant="secondary" loading={pending || runningSince !== null} onClick={onRequest}>
          {t(assist ? 'reviewAssist.rerun' : 'reviewAssist.run')}
        </Button>
      ) : null}
      {runningSince !== null && slowSince === runningSince ? (
        <span className="text-sm text-muted-foreground">{t('reviewAssist.stillWorking')}</span>
      ) : null}
    </>
  );
}

export function AssistSummary({ assist, forbidden, canRetry, onRetry }: { assist: ReviewAssist | null; forbidden: boolean; canRetry: boolean; onRetry: () => void }) {
  const { t } = useTranslation();
  if (forbidden) return <ForbiddenState requiredRole="editor" className="mt-4" />;
  if (!assist) return null;
  if (assist.status === 'failed') return (
    <InlineNotice tone="error" title={t('reviewAssist.failed')} className="mt-4">
      {canRetry ? <Button variant="secondary" size="sm" onClick={onRetry}>{t('reviewAssist.retry')}</Button> : null}
    </InlineNotice>
  );
  if (assist.status !== 'done' && assist.status !== 'partial') return null;
  return (
    <Card className="mt-4 border-info bg-info-soft">
      <CardContent className="space-y-2">
        <p className="font-semibold text-info-strong">{t('reviewAssist.aiLabel')}</p>
        {assist.summary ? <p>{assist.summary}</p> : null}
        <p className="text-sm tabular-nums">{t('reviewAssist.counts', assist.counts)}</p>
        {assist.counts.stale > 0 ? <p className="text-sm text-muted-foreground">{t('reviewAssist.staleCount', { count: assist.counts.stale })}</p> : null}
        {!assist.aiUsed ? <p className="text-sm text-muted-foreground">{t('reviewAssist.rulesOnly')}</p> : null}
        {assist.truncated ? <p className="text-sm text-muted-foreground">{t('reviewAssist.truncated')}</p> : null}
        {assist.status === 'partial' ? <p className="text-sm text-muted-foreground">{t('reviewAssist.partial')}</p> : null}
      </CardContent>
    </Card>
  );
}
