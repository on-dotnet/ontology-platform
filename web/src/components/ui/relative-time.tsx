import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/cn';
import { formatDateTime, formatRecent } from '@/lib/format';

import { Tooltip } from './tooltip';

/** Recent times as "3 分钟前"; the full local time shows on hover (ui-guidelines §6). */
export function RelativeTime({ value, className }: { value: string; className?: string }) {
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  return (
    <Tooltip content={formatDateTime(value, locale)}>
      <time dateTime={value} className={cn('tabular-nums', className)}>
        {formatRecent(value, locale)}
      </time>
    </Tooltip>
  );
}
