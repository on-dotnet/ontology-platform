import { useTranslation } from 'react-i18next';

import { Badge, type BadgeTone } from '@/components/ui/badge';
import { formatDateTime, formatRecent } from '@/lib/format';

import type { Check } from './api';
import { cqMessage } from './error-message';

const tones: Record<Check['result'], BadgeTone> = {
  pending: 'info', pass: 'success', fail: 'error', unanswerable: 'warning', error: 'error',
};

export function CheckResult({ check }: { check: Check | null }) {
  const { t, i18n } = useTranslation();
  if (!check) return <Badge>{t('cq.unchecked')}</Badge>;
  const { detail, result } = check;
  const when = check.finishedAt ?? check.createdAt;
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-1">
        <Badge tone={tones[result]}>{t(`cq.result.${result}`)}</Badge>
        {check.stale && <Badge tone="warning" title={t('cq.staleVersion')}>{t('cq.oldVersion')}</Badge>}
      </div>
      <div className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
        <span>{t('cq.version', { version: check.release.version })}</span>
        <time dateTime={when} title={formatDateTime(when, i18n.language)}>{formatRecent(when, i18n.language)}</time>
      </div>
      {detail && result === 'fail' && <details className="text-sm">
        <summary className="w-fit cursor-pointer rounded text-primary-strong">{t('cq.differences')}</summary>
        <ul className="mt-1 space-y-1 break-words">
          {detail.errorCode && <li>{cqMessage(i18n, detail.errorCode)}</li>}
          {detail.actual !== null && <li>{t('cq.actual', { value: detail.actual })}</li>}
          {detail.missing.length > 0 && <li>{t('cq.missing', { keys: detail.missing.join(t('common.listSeparator')) })}</li>}
          {detail.extra.length > 0 && <li>{t('cq.extra', { keys: detail.extra.join(t('common.listSeparator')) })}</li>}
        </ul>
      </details>}
      {result === 'error' && detail?.errorCode && <p className="text-sm">{cqMessage(i18n, detail.errorCode)}</p>}
    </div>
  );
}
