import { Link } from '@tanstack/react-router';
import { History } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/states/empty-state';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { QueryResult } from '@/features/explore/query-result';

import { useMetricsCatalog } from './api';
import { MetricTable } from './metric-table';
import { RuleCheck } from './rule-check';

export function MetricsPanel({ ontologyId }: { ontologyId: string }) {
  const { t } = useTranslation();
  const catalog = useMetricsCatalog(ontologyId);
  return (
    <QueryResult query={catalog} id={ontologyId} keepMetadata>
      {(data) => data ? (
        <div key={ontologyId} className="space-y-6">
          <Card>
            <CardHeader><CardTitle>{t('metrics.title')}</CardTitle></CardHeader>
            <CardContent>
              <MetricTable id={ontologyId} releaseId={data.release.id} metrics={data.metrics} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>{t('metrics.rules')}</CardTitle></CardHeader>
            <CardContent>
              <RuleCheck id={ontologyId} releaseId={data.release.id} types={data.types} />
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card><EmptyState icon={History} title={t('explore.noRelease')} action={
          <Link to="/releases" search={{ ontology: ontologyId }} className={buttonVariants()}>{t('explore.publish')}</Link>
        } /></Card>
      )}
    </QueryResult>
  );
}
