import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { cn } from '@/lib/cn';
import { useDocumentTitle } from '@/lib/use-document-title';

interface PageHeaderProps {
  title: string;
  /** Short explanation behind the ⓘ icon instead of permanent text (ui-guidelines §4). */
  info?: ReactNode;
  /** At most one primary action (ui-guidelines §1). */
  actions?: ReactNode;
  /** Browser tab title when it should differ from the heading. */
  documentTitle?: string;
  className?: string;
}

export function PageHeader({ title, info, actions, documentTitle, className }: PageHeaderProps) {
  const { t } = useTranslation();
  useDocumentTitle(documentTitle ?? title);
  return (
    <div className={cn('mb-6 flex flex-wrap items-center gap-x-4 gap-y-3', className)}>
      <div className="flex min-w-0 items-center gap-1.5">
        <h1 className="truncate text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {info ? (
          <InfoTip label={t('common.aboutPage', { title: documentTitle ?? title })} side="bottom">
            {info}
          </InfoTip>
        ) : null}
      </div>
      {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
