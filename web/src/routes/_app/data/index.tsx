import { createFileRoute } from '@tanstack/react-router';

import { DataSourcesPage } from '@/features/datasources/data-sources-page';

export const Route = createFileRoute('/_app/data/')({
  component: DataSourcesPage,
});
