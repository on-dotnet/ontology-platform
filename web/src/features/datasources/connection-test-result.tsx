import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { codeMessage } from '@/i18n/error-message';

type Result = components['schemas']['ConnectionTest'];

export function ConnectionTestResult({ result, action }: { result: Result; action?: ReactNode }) {
  const { t, i18n } = useTranslation();
  const { reason } = result;
  return (
    <div className="space-y-2">
      {result.ok ? (
        <InlineNotice tone="success" title={t('datasources.test.ok')}>
          {result.serverVersion
            ? t('datasources.test.version', { version: result.serverVersion })
            : undefined}
        </InlineNotice>
      ) : (
        <InlineNotice tone="error" action={action}>
          {reason ? t(`datasources.test.reason.${reason}`) : codeMessage(i18n, result.code, 'errors.datasource.connect_failed')}
        </InlineNotice>
      )}
      {result.warnings.includes('account_can_write') && (
        <InlineNotice tone="warning">{t('datasources.test.writeWarning')}</InlineNotice>
      )}
    </div>
  );
}
