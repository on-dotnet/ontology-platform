import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { EmptyState, type StateTone } from '@/components/states/empty-state';
import { Card } from '@/components/ui/card';

export type ComingSoonSection = 'data' | 'explore';

interface ComingSoonPageProps {
  section: ComingSoonSection;
  icon: LucideIcon;
  tone?: StateTone;
}

/** Placeholder for sections that are not built yet: page header with ⓘ plus one sentence on what the page will do. No sample data. */
export function ComingSoonPage({ section, icon, tone = 'primary' }: ComingSoonPageProps) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t(`nav.${section}`)} info={t(`pages.${section}.info`)} />
      <Card>
        <EmptyState
          icon={icon}
          tone={tone}
          badge={t('common.comingSoon')}
          title={t(`pages.${section}.emptyTitle`)}
          description={t(`pages.${section}.emptyDescription`)}
          className="py-20"
        />
      </Card>
    </>
  );
}
