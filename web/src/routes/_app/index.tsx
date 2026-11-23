import { createFileRoute } from '@tanstack/react-router';

import { WorkbenchPage } from '@/features/workbench/workbench-page';

export const Route = createFileRoute('/_app/')({
  component: WorkbenchPage,
});
