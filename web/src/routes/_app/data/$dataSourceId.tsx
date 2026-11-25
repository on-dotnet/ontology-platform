import { createFileRoute } from '@tanstack/react-router';

import { DataSourceDetailPage } from '@/features/datasources/data-source-detail-page';

export const Route = createFileRoute('/_app/data/$dataSourceId')({
  component: DataSourceDetailRoute,
});

function DataSourceDetailRoute() {
  const { dataSourceId } = Route.useParams();
  return <DataSourceDetailPage key={dataSourceId} dataSourceId={dataSourceId} />;
}
