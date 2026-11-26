import { Link } from '@tanstack/react-router';
import { Calculator } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { EmptyState } from '@/components/states/empty-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Pagination } from '@/components/ui/pagination';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePermissions } from '@/features/auth/permissions';
import { usePagination } from '@/lib/pagination';

import { useMetricValue } from './api';
import { MetricResult } from './metric-result';
import { ReadResult } from './read-result';

type Metric = components['schemas']['MetricInfo'];
interface Context {
  id: string;
  releaseId: string;
}

function MetricRow({ id, releaseId, metric }: Context & { metric: Metric }) {
  const { t } = useTranslation();
  const [requested, setRequested] = useState(false);
  const query = useMetricValue(id, releaseId, metric.metricId, requested);
  const calculate = () => {
    if (requested) void query.refetch();
    else setRequested(true);
  };
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{metric.label}</TableCell>
        <TableCell>{metric.subjectTypeLabel}</TableCell>
        <TableCell>{t(`metrics.aggregates.${metric.aggregate}`)}</TableCell>
        <TableCell className="text-right">
          <Button variant="secondary" size="sm" loading={query.isFetching} onClick={calculate}>{t('metrics.evaluate')}</Button>
        </TableCell>
      </TableRow>
      {requested && <TableRow><TableCell colSpan={4} className="bg-muted/50">
        <ReadResult query={query} onRestart={query.retryWithCatalog}>{(value) => <MetricResult result={value} />}</ReadResult>
      </TableCell></TableRow>}
    </>
  );
}

export function MetricTable({ metrics, ...context }: Context & { metrics: Metric[] }) {
  const { t } = useTranslation();
  const { canUpload } = usePermissions();
  const page = usePagination(metrics.length);
  if (!metrics.length) return <EmptyState icon={Calculator} headingLevel="h3" title={t('metrics.noMetrics')} action={
    canUpload && <Link to="/ontology" search={{ ontology: context.id, view: 'list' }} className={buttonVariants()}>{t('metrics.create')}</Link>
  } />;
  return (
    <>
      <Table aria-label={t('metrics.title')}>
        <TableHeader><TableRow>
          <TableHead>{t('metrics.name')}</TableHead><TableHead>{t('metrics.subject')}</TableHead>
          <TableHead>{t('metrics.aggregate')}</TableHead><TableHead className="text-right">{t('ontologyPage.list.columns.actions')}</TableHead>
        </TableRow></TableHeader>
        <TableBody>{metrics.slice(page.start, page.end).map((metric) => <MetricRow key={metric.metricId} metric={metric} {...context} />)}</TableBody>
      </Table>
      <Pagination state={page} total={metrics.length} />
    </>
  );
}
