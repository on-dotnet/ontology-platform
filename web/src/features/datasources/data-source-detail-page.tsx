import { Database } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { Card } from '@/components/ui/card';

interface DataSourceDetailPageProps {
  dataSourceId: string;
}

/** One data source: connection, catalog, AI binding suggestions (spec 003, 12.1). A placeholder
 * until M3 batch 3 builds it. */
export function DataSourceDetailPage(_props: DataSourceDetailPageProps) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t('datasources.title')} info={t('datasources.detailInfo')} />
      <Card>
        <EmptyState
          icon={Database}
          tone="success"
          badge={t('common.comingSoon')}
          title={t('datasources.detailEmptyTitle')}
          description={t('datasources.detailEmptyDescription')}
          className="py-20"
        />
      </Card>
    </>
  );
}
