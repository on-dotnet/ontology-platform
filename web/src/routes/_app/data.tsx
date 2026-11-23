import { createFileRoute } from '@tanstack/react-router';
import { Database } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/data')({
  component: () => <ComingSoonPage section="data" icon={Database} tone="success" />,
});
